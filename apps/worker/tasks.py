import asyncio
import uuid
import os
import boto3
from apps.api.core.config import settings
from apps.worker.ingestion.code import process_repo
from apps.worker.ingestion.doc import process_pdf
from apps.api.services.embedding import get_embedding_provider
from apps.api.services.vector_db import upsert_vectors, ensure_collection
from apps.api.services.sparse_db import index_document, ensure_index
from qdrant_client.models import PointStruct
from apps.api.core.database import SessionLocal
from apps.api.models.ingestion import IngestionJob
from sqlalchemy.sql import func

BUCKET_NAME = "ingestion"

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ROOT_USER,
        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD
    )

def update_job_status(job_id: str, status: str):
    db = SessionLocal()
    try:
        job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        if job:
            job.status = status
            if status == "running":
                job.started_at = func.now()
            elif status in ["completed", "failed"]:
                job.completed_at = func.now()
            db.commit()
    except Exception as e:
        print(f"Error updating job status: {e}")
    finally:
        db.close()

async def ingest_repo(ctx, job_id: str, source_id: str, repo_url: str, collection_name: str = "test_collection"):
    print(f"Starting repo ingestion for {repo_url} (Job {job_id})")
    update_job_status(job_id, "running")

    try:
        # 1. Process Repo
        chunks = await asyncio.to_thread(process_repo, repo_url)
        print(f"Generated {len(chunks)} chunks")

        if not chunks:
            print("No chunks generated")
            update_job_status(job_id, "completed")
            return

        # 2. Embed
        texts = [c["text"] for c in chunks]
        provider = get_embedding_provider()
        embeddings = await provider.embed(texts)

        # 3. Index
        # Ensure collections exist
        ensure_collection(collection_name)
        ensure_index(collection_name)

        points = []
        for i, chunk in enumerate(chunks):
            doc_id = str(uuid.uuid4())
            vector = embeddings[i]
            payload = chunk["metadata"]
            payload["text"] = chunk["text"]
            payload["source_id"] = source_id

            # Dense
            points.append(PointStruct(id=doc_id, vector=vector, payload=payload))

            # Sparse
            index_document(collection_name, doc_id, payload)

        upsert_vectors(collection_name, points)
        print(f"Ingested {len(points)} vectors to {collection_name}")
        update_job_status(job_id, "completed")

    except Exception as e:
        print(f"Job {job_id} failed: {e}")
        update_job_status(job_id, "failed")
        raise e

async def ingest_doc(ctx, job_id: str, source_id: str, file_path: str, collection_name: str = "test_collection"):
    print(f"Starting doc ingestion for {file_path} (Job {job_id})")
    update_job_status(job_id, "running")

    local_path = None
    try:
        # 0. Download from S3 if needed
        # Assume if it looks like a key (contains /) or we want to try S3 first
        # But for local dev it might be a path.
        # However, the API now returns a key.
        s3 = get_s3_client()
        local_path = f"/tmp/{os.path.basename(file_path)}"

        try:
             s3.download_file(BUCKET_NAME, file_path, local_path)
             print(f"Downloaded {file_path} to {local_path}")
        except Exception as e:
             # Fallback: maybe it IS a local path (if manually triggered)?
             # Or if bucket fails.
             print(f"S3 download failed ({e}), assuming local path or failing.")
             if not os.path.exists(file_path):
                 if os.path.exists(local_path):
                     pass # Downloaded
                 else:
                     raise Exception(f"File not found: {file_path}")
             else:
                 local_path = file_path

        # 1. Process PDF
        chunks = await asyncio.to_thread(process_pdf, local_path)

        texts = [c["text"] for c in chunks]
        provider = get_embedding_provider()
        embeddings = await provider.embed(texts)

        ensure_collection(collection_name)
        ensure_index(collection_name)

        points = []
        for i, chunk in enumerate(chunks):
            doc_id = str(uuid.uuid4())
            vector = embeddings[i]
            payload = chunk["metadata"]
            payload["text"] = chunk["text"]
            payload["source_id"] = source_id

            points.append(PointStruct(id=doc_id, vector=vector, payload=payload))
            index_document(collection_name, doc_id, payload)

        upsert_vectors(collection_name, points)
        print(f"Ingested {len(points)} vectors to {collection_name}")
        update_job_status(job_id, "completed")

    except Exception as e:
        print(f"Job {job_id} failed: {e}")
        update_job_status(job_id, "failed")
        raise e
    finally:
        if local_path and os.path.exists(local_path) and local_path.startswith("/tmp/"):
            try:
                os.remove(local_path)
            except:
                pass
