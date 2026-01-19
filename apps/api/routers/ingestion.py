from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from arq.connections import ArqRedis, create_pool
from apps.api.core.config import settings
from typing import Optional

router = APIRouter()

class IngestCodeRequest(BaseModel):
    repo_url: str
    source_id: str = "default_source" # Simplified for MVP
    collection_name: str = "test_collection"

class IngestDocRequest(BaseModel):
    file_path: str # In real app, this would be a key from MinIO after upload
    source_id: str = "default_doc_source"
    collection_name: str = "test_collection"

async def get_redis():
    redis = await create_pool(RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD
    ))
    try:
        yield redis
    finally:
        await redis.close()

from arq import create_pool
from arq.connections import RedisSettings

# Helper to enqueue
async def enqueue_job(function: str, *args):
    redis = await create_pool(RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD
    ))
    await redis.enqueue_job(function, *args)
    await redis.close()

@router.post("/code")
async def ingest_code(req: IngestCodeRequest):
    # Enqueue job
    await enqueue_job('ingest_repo', "default_job_id", req.source_id, req.repo_url, req.collection_name)
    return {"status": "queued", "type": "code", "repo": req.repo_url}

@router.post("/doc")
async def ingest_doc(req: IngestDocRequest):
    await enqueue_job('ingest_doc', "default_job_id", req.source_id, req.file_path, req.collection_name)
    return {"status": "queued", "type": "doc", "file": req.file_path}
