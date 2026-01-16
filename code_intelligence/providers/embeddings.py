import logging
import hashlib
import numpy as np
from typing import List
from openai import OpenAI, RateLimitError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
from ..config import settings

logger = logging.getLogger(__name__)

class EmbeddingsInterface:
    """Interface for Embeddings (OpenAI/OpenRouter/Local)."""

    def __init__(self):
        self.provider = settings.get_embeddings_provider()
        self.api_key = settings.get_llm_api_key()
        self.base_url = settings.get_llm_base_url()
        self.client = self._create_client()

    def _create_client(self) -> OpenAI | None:
        if self.provider == "local" or not self.api_key:
             return None

        headers = {}
        if self.provider == "openrouter":
             if settings.openrouter_http_referer:
                headers["HTTP-Referer"] = settings.openrouter_http_referer
             if settings.openrouter_x_title:
                headers["X-Title"] = settings.openrouter_x_title

        return OpenAI(
            api_key=self.api_key.get_secret_value(),
            base_url=self.base_url,
            default_headers=headers or None,
            max_retries=0,
        )

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.client:
            return self._stub_embed(texts)

        try:
            response = self.client.embeddings.create(
                input=texts,
                model=settings.embeddings_model
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"Embeddings failed: {e}")
            raise e

    def _stub_embed(self, texts: List[str]) -> List[List[float]]:
        """Deterministic hash-based embedding for testing."""
        dim = 1536
        embeddings = []
        for text in texts:
            # Seed based on text hash
            h = hashlib.sha256(text.encode("utf-8")).digest()
            # Use part of hash as seed
            seed = int.from_bytes(h[:4], "big")
            rng = np.random.default_rng(seed)

            # Create a random vector
            vec = rng.random(dim).astype(np.float32)
            # Normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            embeddings.append(vec.tolist())
        return embeddings
