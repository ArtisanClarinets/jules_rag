import asyncio
import uuid
from apps.api.core.config import settings
from apps.worker.ingestion.code import process_repo
from apps.worker.ingestion.doc import process_pdf
from apps.api.services.embedding import get_embedding_provider
from apps.api.services.vector_db import upsert_vectors, ensure_collection
from apps.api.services.sparse_db import index_document, ensure_index
from qdrant_client.models import PointStruct

async def ingest_repo(ctx, job_id: str, source_id: str, repo_url: str, collection_name: str = "test_collection"):
    print(f"Starting repo ingestion for {repo_url} (Job {job_id})")

    # 1. Process Repo
    chunks = await asyncio.to_thread(process_repo, repo_url)
    print(f"Generated {len(chunks)} chunks")

    if not chunks:
        print("No chunks generated")
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

async def ingest_doc(ctx, job_id: str, source_id: str, file_path: str, collection_name: str = "test_collection"):
    print(f"Starting doc ingestion for {file_path} (Job {job_id})")

    # 1. Process PDF
    # In real app, download from MinIO using file_path (key)
    # For now assume local path or mocked
    chunks = await asyncio.to_thread(process_pdf, file_path)

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
