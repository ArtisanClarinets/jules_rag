from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Any
from apps.api.core.database import get_db
from apps.api.services.retrieval import hybrid_search

router = APIRouter()

class SearchRequest(BaseModel):
    query: str
    collection_name: str
    limit: int = 10
    rerank: bool = True

class SearchResponse(BaseModel):
    results: List[Any]

@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    try:
        results = await hybrid_search(
            collection_name=req.collection_name,
            query=req.query,
            limit=req.limit,
            rerank=req.rerank
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
