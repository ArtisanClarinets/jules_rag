from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union
import time

from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from pydantic import SecretStr
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .config import settings

logger = logging.getLogger(__name__)

_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}\s*$")


class LLMInterface:
    """Unified interface for OpenAI and OpenRouter."""

    def __init__(self):
        self.api_key = settings.get_llm_api_key()
        self.base_url = settings.get_llm_base_url()
        self.client = self._create_client()

    def _create_client(self) -> OpenAI | None:
        if not self.api_key:
            logger.warning("No API key configured for LLM provider. Using simulation mode.")
            return None

        headers = {}
        if settings.llm_provider == "openrouter":
            if settings.openrouter_http_referer:
                headers["HTTP-Referer"] = settings.openrouter_http_referer
            if settings.openrouter_x_title:
                headers["X-Title"] = settings.openrouter_x_title

        return OpenAI(
            api_key=self.api_key.get_secret_value(),
            base_url=self.base_url,
            default_headers=headers or None,
            max_retries=0, # We handle retries manually with tenacity
        )

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def generate_response(
        self,
        prompt: str,
        system_prompt: str = "You are a coding expert.",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Generate a response from the LLM."""

        if not self.client:
            return self._heuristic_simulation(prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

        # 1. Try strict JSON mode if requested and preferred
        if json_mode and settings.llm_prefer_json:
            try:
                response = self.client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=tokens,
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content or "{}"
            except APIError as e:
                # If the model doesn't support json_object, it might return 400.
                # In that case, we fall back to standard generation + instruction.
                logger.debug(f"JSON mode failed or unsupported: {e}")
                pass

        # 2. Fallback: Prompt engineering for JSON
        if json_mode:
             messages.append({
                "role": "system",
                "content": "You must return valid JSON only. Do not wrap in markdown code blocks.",
            })

        try:
            response = self.client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
            )
            txt = response.choices[0].message.content or ""

            if json_mode:
                return self._coerce_json(txt)
            return txt

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            if json_mode:
                return json.dumps({"error": str(e), "is_valid": False})
            raise e

    def _coerce_json(self, txt: str) -> str:
        txt = txt.strip()

        # Remove markdown code blocks if present
        if txt.startswith("```json"):
            txt = txt[7:]
        if txt.startswith("```"):
            txt = txt[3:]
        if txt.endswith("```"):
            txt = txt[:-3]
        txt = txt.strip()

        # Happy path
        try:
            json.loads(txt)
            return txt
        except Exception:
            pass

        # Try to extract the last JSON object
        m = _JSON_OBJ_RE.search(txt)
        if m:
            candidate = m.group(0)
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

        # Wrap as object
        return json.dumps({"response": txt})

    def _heuristic_simulation(self, prompt: str) -> str:
        """Simulation mode for when no API key is present."""
        logger.info("Running in simulation mode (no API key).")
        p = prompt.lower()
        if "rate the relevance" in p:
             return json.dumps(
                {
                    "score": 0.9,
                    "reasoning": "Heuristic match (simulation mode). Set LLM_PROVIDER + API key for real inference.",
                }
            )
        return json.dumps({"response": "Simulated LLM response (configure a provider key)"})


class EmbeddingsInterface:
    """Interface for Embeddings (OpenAI/OpenRouter)."""

    def __init__(self):
        # Determine provider for embeddings
        self.provider = settings.get_embeddings_provider()

        # Use the same logic for API key and base URL as LLM if same provider,
        # otherwise we might need specific logic.
        # For now, we assume if provider is same as LLM, reuse credentials.

        self.api_key = settings.get_llm_api_key()
        self.base_url = settings.get_llm_base_url()

        # If explicitly using OpenAI while LLM is OpenRouter (or vice versa),
        # we might need to adjust. But `settings.get_embeddings_provider()` defaults to LLM provider.

        self.client = self._create_client()

    def _create_client(self) -> OpenAI | None:
        if not self.api_key:
             return None

        headers = {}
        # OpenRouter docs say embeddings endpoint is compatible.
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
            # Random embeddings for simulation
            return [[0.1] * 1536 for _ in texts]

        # Batching is handled by caller or we can do it here.
        # OpenAI suggests max 2048 dimensions for some models, but input list size is also limited.

        # OpenRouter uses `https://openrouter.ai/api/v1/embeddings`

        try:
            response = self.client.embeddings.create(
                input=texts,
                model=settings.embeddings_model
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"Embeddings failed: {e}")
            raise e
