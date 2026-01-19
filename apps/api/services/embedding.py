from typing import List
import httpx
from abc import ABC, abstractmethod
from apps.api.core.config import settings

class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        pass

class TEIProvider(EmbeddingProvider):
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def embed(self, texts: List[str]) -> List[List[float]]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/embed",
                json={"inputs": texts},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

class OpenAIProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small", base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def embed(self, texts: List[str]) -> List[List[float]]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"input": texts, "model": self.model},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            # Ensure order
            return [d["embedding"] for d in data["data"]]

def get_embedding_provider(provider_type: str = None) -> EmbeddingProvider:
    ptype = provider_type or settings.EMBEDDING_PROVIDER

    if ptype == "local_cpu":
        return TEIProvider(base_url="http://embedding-cpu:80")
    elif ptype == "local_gpu":
        # Assumes gpu profile is up and service named embedding-gpu
        return TEIProvider(base_url="http://embedding-gpu:80")
    elif ptype == "openrouter":
        return OpenAIProvider(
            api_key=settings.OPENROUTER_API_KEY, # Needs to be passed or loaded
            base_url="https://openrouter.ai/api/v1",
            model="openai/text-embedding-3-small" # Configurable?
        )
    else:
        # Fallback to local cpu
        return TEIProvider(base_url="http://embedding-cpu:80")

class RerankProvider(ABC):
    @abstractmethod
    async def rerank(self, query: str, texts: List[str]) -> List[dict]:
        # Returns list of {index: int, score: float}
        pass

class TEIRerankProvider(RerankProvider):
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def rerank(self, query: str, texts: List[str]) -> List[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/rerank",
                json={"query": query, "texts": texts},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

def get_rerank_provider(provider_type: str = None) -> RerankProvider:
    ptype = provider_type or settings.RERANK_PROVIDER

    if ptype == "local_cpu":
        return TEIRerankProvider(base_url="http://rerank-cpu:80")
    # Add others as needed
    return TEIRerankProvider(base_url="http://rerank-cpu:80")
