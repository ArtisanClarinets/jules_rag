from qdrant_client import QdrantClient, models
from apps.api.core.config import settings

client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

def ensure_collection(collection_name: str, vector_size: int = 1024):
    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)

    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE
            )
        )

def upsert_vectors(collection_name: str, points: list):
    client.upsert(
        collection_name=collection_name,
        points=points
    )

def search_vectors(collection_name: str, vector: list, limit: int = 10):
    return client.search(
        collection_name=collection_name,
        query_vector=vector,
        limit=limit
    )
