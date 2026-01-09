from __future__ import annotations

from typing import Iterable, List, Optional

import numpy as np
from openai import OpenAI

from .config import EmbeddingsConfig, load_embeddings_config


class EmbeddingClient:
    """Embeddings wrapper for OpenAI-compatible providers.

    Supports OpenAI and OpenRouter through the same codepath by changing
    base_url + api_key.
    """

    def __init__(self, cfg: Optional[EmbeddingsConfig] = None):
        self.cfg = cfg or load_embeddings_config()

        api_key = self.cfg.provider.api_key
        if not api_key:
            self.client = None
            return

        headers = {}
        if self.cfg.provider.provider == "openrouter":
            if self.cfg.provider.http_referer:
                headers["HTTP-Referer"] = self.cfg.provider.http_referer
            if self.cfg.provider.x_title:
                headers["X-Title"] = self.cfg.provider.x_title

        self.client = OpenAI(
            api_key=api_key,
            base_url=self.cfg.provider.base_url,
            default_headers=headers or None,
        )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        if not self.client:
            raise RuntimeError("EmbeddingClient is not configured. Set EMBEDDINGS_PROVIDER + API key.")

        resp = self.client.embeddings.create(model=self.cfg.model, input=texts)
        # OpenAI-compatible embeddings return a list of {embedding: [...]}.
        vecs: List[np.ndarray] = []
        for item in resp.data:
            vecs.append(np.asarray(item.embedding, dtype=np.float32))
        return vecs

    def embed_text(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]
