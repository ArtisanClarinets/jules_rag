from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, UploadFile
from pydantic import BaseModel
from arq.connections import ArqRedis, create_pool
from apps.api.core.config import settings
from typing import Optional, List, Any
from sqlalchemy.orm import Session
from apps.api.core.database import get_db
from apps.api.models.ingestion import Source, IngestionJob, Collection
import uuid
import shutil
import os
import boto3
from botocore.exceptions import NoCredentialsError

router = APIRouter()

class IngestCodeRequest(BaseModel):
    repo_url: str
    source_id: str = "default_source"
    collection_name: str = "test_collection"

class IngestDocRequest(BaseModel):
    file_path: str
    source_id: str = "default_doc_source"
    collection_name: str = "test_collection"

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

# MinIO Client
BUCKET_NAME = "ingestion"

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ROOT_USER,
        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD
    )

def ensure_bucket():
    s3 = get_s3_client()
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
    except:
        try:
            s3.create_bucket(Bucket=BUCKET_NAME)
        except Exception as e:
            print(f"Failed to create bucket: {e}")

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ensure_bucket()
    # Sanitize filename
    safe_filename = os.path.basename(file.filename)
    # Use UUID prefix to avoid collisions
    key = f"{uuid.uuid4()}/{safe_filename}"

    try:
        s3 = get_s3_client()
        s3.upload_fileobj(file.file, BUCKET_NAME, key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return {"file_path": key}

@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(50).all()
    # Manual serialization to avoid circular deps or lazy loading issues
    res = []
    for job in jobs:
        res.append({
            "id": job.id,
            "source_id": job.source_id,
            "status": job.status,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at
        })
    return res

@router.post("/code")
async def ingest_code(req: IngestCodeRequest, db: Session = Depends(get_db)):
    # Ensure Collection
    collection = db.query(Collection).filter(Collection.name == req.collection_name).first()
    if not collection:
        collection = Collection(name=req.collection_name)
        db.add(collection)
        db.commit()
        db.refresh(collection)

    # Ensure Source
    source = db.query(Source).filter(Source.id == req.source_id).first()
    if not source:
        source = Source(id=req.source_id, name=req.source_id, type="code", config={"repo_url": req.repo_url}, collection_id=collection.id)
        db.add(source)
    else:
        source.config = {"repo_url": req.repo_url}
        source.collection_id = collection.id

    db.commit()

    job_id = str(uuid.uuid4())
    job = IngestionJob(id=job_id, source_id=source.id, status="pending")
    db.add(job)
    db.commit()

    # Enqueue job
    await enqueue_job('ingest_repo', job_id, req.source_id, req.repo_url, req.collection_name)
    return {"status": "queued", "type": "code", "repo": req.repo_url, "job_id": job_id}

@router.post("/doc")
async def ingest_doc(req: IngestDocRequest, db: Session = Depends(get_db)):
    # Ensure Collection
    collection = db.query(Collection).filter(Collection.name == req.collection_name).first()
    if not collection:
        collection = Collection(name=req.collection_name)
        db.add(collection)
        db.commit()
        db.refresh(collection)

    # Ensure Source
    source = db.query(Source).filter(Source.id == req.source_id).first()
    if not source:
        source = Source(id=req.source_id, name=req.source_id, type="doc", config={"file_path": req.file_path}, collection_id=collection.id)
        db.add(source)
    else:
        source.config = {"file_path": req.file_path}
        source.collection_id = collection.id

    db.commit()

    job_id = str(uuid.uuid4())
    job = IngestionJob(id=job_id, source_id=source.id, status="pending")
    db.add(job)
    db.commit()

    await enqueue_job('ingest_doc', job_id, req.source_id, req.file_path, req.collection_name)
    return {"status": "queued", "type": "doc", "file": req.file_path, "job_id": job_id}
