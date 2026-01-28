import os
import logging
import json
import time
import asyncio
import threading
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from code_intelligence.db import Database
from code_intelligence.indexing import FileIndexer
from code_intelligence.retrieval import RetrievalEngine
from code_intelligence.answer import AnswerEngine
from code_intelligence.classifier import QueryClassifier
from code_intelligence.workflow import WorkflowEngine
from code_intelligence.config import settings

from pythonjsonlogger import jsonlogger

# Logging Setup
logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s %(request_id)s %(duration_ms)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# State
db: Optional[Database] = None
indexer: Optional[FileIndexer] = None
retriever: Optional[RetrievalEngine] = None
answer_engine: Optional[AnswerEngine] = None
classifier: Optional[QueryClassifier] = None
workflow_engine: Optional[WorkflowEngine] = None

# Rate Limit State
RATE_LIMIT_STORE = {}
RATE_LIMIT_CAPACITY = 50.0
RATE_LIMIT_RATE = 1.0

def check_rate_limit(key: str) -> bool:
    now = time.time()
    tokens, last_update = RATE_LIMIT_STORE.get(key, (RATE_LIMIT_CAPACITY, now))
    elapsed = now - last_update
    tokens = min(RATE_LIMIT_CAPACITY, tokens + elapsed * RATE_LIMIT_RATE)

    if tokens >= 1.0:
        RATE_LIMIT_STORE[key] = (tokens - 1.0, now)
        return True

    RATE_LIMIT_STORE[key] = (tokens, now)
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, indexer, retriever, answer_engine, classifier, workflow_engine
    logger.info("Initializing Backend...")
    db = Database(settings.db_path)
    indexer = FileIndexer(db)
    retriever = RetrievalEngine(db)
    answer_engine = AnswerEngine()
    classifier = QueryClassifier()
    workflow_engine = WorkflowEngine(retriever)
    yield
    logger.info("Shutting down...")

app = FastAPI(title="Code RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---

class IndexRequest(BaseModel):
    path: str
    force: bool = False

class QueryRequest(BaseModel):
    query: str
    k: int = 10
    stream: bool = False

class QueryResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]

class SearchRequest(BaseModel):
    query: str
    k: int = 10

class MCPCallRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any] = {}
    id: Optional[Any] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "vantus-rag"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: float = 0.0

# --- Middleware ---

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    # Auth Logic
    api_key = request.headers.get("x-api-key") or request.headers.get("Authorization")
    if api_key and api_key.startswith("Bearer "):
        api_key = api_key.split(" ")[1]

    valid = False

    # 1. Check legacy token
    if settings.rag_api_token and api_key and api_key == settings.rag_api_token.get_secret_value():
        valid = True

    # 2. Check key list
    if not valid and settings.rag_api_keys and api_key:
        for k in settings.rag_api_keys:
            if api_key == k.get_secret_value():
                valid = True
                break

    # 3. If no auth configured, allow
    if not settings.rag_api_token and not settings.rag_api_keys:
        valid = True

    if not valid:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # Rate Limiting
    if api_key and not check_rate_limit(api_key):
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded"})

    response = await call_next(request)
    return response

# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok", "provider": settings.llm_provider}

@app.post("/index")
async def trigger_indexing(req: IndexRequest, background_tasks: BackgroundTasks):
    if not os.path.isdir(req.path):
        raise HTTPException(status_code=400, detail="Invalid path")

    background_tasks.add_task(run_indexing, req.path, req.force)
    return {"status": "indexing_started", "path": req.path}

def run_indexing(path: str, force: bool):
    logger.info(f"Starting indexing for {path}")
    try:
        stats = indexer.index_workspace(path, force=force)
        logger.info(f"Indexing complete: {stats}")
    except Exception as e:
        logger.error(f"Indexing failed: {e}")

@app.post("/query", response_model=QueryResponse)
async def query_codebase(req: QueryRequest):
    if not retriever or not answer_engine or not classifier or not workflow_engine:
         raise HTTPException(status_code=503, detail="Not initialized")

    logger.info(f"Query: {req.query}")

    # 1. Classify
    try:
        class_res = await asyncio.to_thread(classifier.classify, req.query)
        category = class_res.get("category", "CODE")
        logger.info(f"Query classified as: {category} (Reason: {class_res.get('reasoning')})")
    except Exception as e:
        logger.error(f"Classification error: {e}")
        category = "CODE"

    # 2. Execute Workflow if applicable
    if category in ["PLAN", "DOCS"]:
        try:
            # Workflow engine run is now async
            result = await workflow_engine.run(category, req.query)
            if result:
                return QueryResponse(
                    answer=result["answer"],
                    citations=result.get("citations", [])
                )
        except Exception as e:
            logger.error(f"Workflow failed: {e}, falling back to standard search.")

    # 3. Standard Retrieval & Answer
    results = await retriever.retrieve(req.query, k=req.k)
    output = await asyncio.to_thread(answer_engine.answer, req.query, results)

    return QueryResponse(
        answer=output["answer"],
        citations=output["citations"]
    )

@app.post("/query_stream")
async def query_stream_endpoint(req: QueryRequest):
    if not retriever or not answer_engine:
         raise HTTPException(status_code=503, detail="Not initialized")

    async def event_generator():
        yield json.dumps({"type": "retrieval_start", "query": req.query}) + "\n"

        try:
            results = await retriever.retrieve(req.query, k=req.k)

            items = []
            for r in results:
                items.append({
                    "path": r.node.filepath,
                    "lines": [r.node.start_line, r.node.end_line],
                    "score": r.score,
                    "route": r.node.next_route_path,
                    "segment": r.node.next_segment_type
                })
            yield json.dumps({"type": "retrieval_result", "items": items}) + "\n"

            accumulated_answer = ""

            # Run synchronous generator in a separate thread to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            queue = asyncio.Queue()

            def producer():
                try:
                    stream = answer_engine.answer_stream(req.query, results)
                    for chunk in stream:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
                    loop.call_soon_threadsafe(queue.put_nowait, None) # Sentinel
                except Exception as e:
                    logger.error(f"Stream generation error: {e}")
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            threading.Thread(target=producer, daemon=True).start()

            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                accumulated_answer += chunk
                yield json.dumps({"type": "generation_chunk", "text": chunk}) + "\n"

            yield json.dumps({"type": "done", "answer": accumulated_answer, "citations": items}) + "\n"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

# --- MCP Support ---

@app.post("/mcp")
async def mcp_endpoint(req: MCPCallRequest):
    if req.method == "rag.search":
        q = req.params.get("query")
        k = req.params.get("k", 5)
        if not q:
            return {"jsonrpc": "2.0", "error": {"code": -32602, "message": "Missing query"}, "id": req.id}

        results = await retriever.retrieve(q, k=k)
        return {
            "jsonrpc": "2.0",
            "result": {
                "results": [
                    {
                        "content": r.node.content,
                        "filepath": r.node.filepath,
                        "lines": [r.node.start_line, r.node.end_line],
                        "score": r.score
                    } for r in results
                ]
            },
            "id": req.id
        }

    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": req.id}

# --- OpenAI Compatible Endpoint ---

@app.post("/v1/chat/completions")
async def openai_chat_completions(req: ChatCompletionRequest):
    if not retriever or not answer_engine:
         raise HTTPException(status_code=503, detail="Not initialized")

    # Extract query from last user message
    query = next((m.content for m in reversed(req.messages) if m.role == "user"), None)
    if not query:
        raise HTTPException(status_code=400, detail="No user message found")

    if req.stream:
        async def stream_generator():
            request_id = f"chatcmpl-{int(time.time())}"
            created = int(time.time())

            # 1. Retrieval
            results = await retriever.retrieve(query, k=5)

            # 2. Generation
            stream = answer_engine.answer_stream(query, results)

            for chunk in stream:
                data = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": req.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None
                        }
                    ]
                }
                yield f"data: {json.dumps(data)}\n\n"

            # Final done message
            data = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": req.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }
                    ]
                }
            yield f"data: {json.dumps(data)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    else:
        # Non-streaming
        results = await retriever.retrieve(query, k=5)
        output = await asyncio.to_thread(answer_engine.answer, query, results)

        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": output["answer"]
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
