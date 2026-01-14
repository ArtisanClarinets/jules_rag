import os
import logging
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

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
    # Simplified MCP JSON-RPC wrapper
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any] = {}
    id: Optional[Any] = None

# --- Middleware ---

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Local Token Auth
    if settings.rag_api_token:
        auth = request.headers.get("Authorization")
        expected = f"Bearer {settings.rag_api_token.get_secret_value()}"
        if auth != expected:
             # Allow health check without auth? Usually yes.
             if request.url.path != "/health":
                 # Return JSON response for 401
                 from fastapi.responses import JSONResponse
                 return JSONResponse(status_code=401, content={"error": "Unauthorized"})

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
        # FileIndexer.index_workspace now handles repo map generation and persistence
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
        class_res = classifier.classify(req.query)
        category = class_res.get("category", "CODE")
        logger.info(f"Query classified as: {category} (Reason: {class_res.get('reasoning')})")
    except Exception as e:
        logger.error(f"Classification error: {e}")
        category = "CODE"

    # 2. Execute Workflow if applicable
    if category in ["PLAN", "DOCS"]:
        try:
            result = workflow_engine.run(category, req.query)
            if result:
                return QueryResponse(
                    answer=result["answer"],
                    citations=result.get("citations", [])
                )
        except Exception as e:
            logger.error(f"Workflow failed: {e}, falling back to standard search.")

    # 3. Standard Retrieval & Answer (CODE/GENERAL or Fallback)
    results = retriever.retrieve(req.query, k=req.k)

    # 4. Answer
    output = answer_engine.answer(req.query, results)

    return QueryResponse(
        answer=output["answer"],
        citations=output["citations"]
    )

# --- MCP Support (Optional Mode) ---
# This endpoint acts as a simple MCP server over HTTP.
# Real MCP usually runs over Stdio or SSE, but HTTP is fine for tools.

@app.post("/mcp")
async def mcp_endpoint(req: MCPCallRequest):
    if req.method == "rag.search":
        q = req.params.get("query")
        k = req.params.get("k", 5)
        if not q:
            return {"jsonrpc": "2.0", "error": {"code": -32602, "message": "Missing query"}, "id": req.id}

        results = retriever.retrieve(q, k=k)
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

    elif req.method == "rag.explain":
        # Simplified explain: just search and answer
        symbol = req.params.get("symbol")
        if not symbol:
             return {"jsonrpc": "2.0", "error": {"code": -32602, "message": "Missing symbol"}, "id": req.id}

        # Reuse query logic
        results = retriever.retrieve(f"Explain {symbol}", k=5)
        output = answer_engine.answer(f"Explain the code symbol '{symbol}'", results)

        return {
            "jsonrpc": "2.0",
            "result": {
                "explanation": output["answer"],
                "citations": output["citations"]
            },
            "id": req.id
        }

    elif req.method == "list_tools":
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {
                        "name": "rag.search",
                        "description": "Search the codebase for code snippets.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "k": {"type": "integer"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "rag.explain",
                        "description": "Explain a symbol or file.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"}
                            },
                            "required": ["symbol"]
                        }
                    }
                ]
            },
            "id": req.id
        }

    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": req.id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
