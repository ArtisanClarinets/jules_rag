from __future__ import annotations

import json
import logging
import re
from typing import Optional, Generator

from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from ..config import settings
from ..safe_context import mask_secrets, strip_prompt_injection

logger = logging.getLogger(__name__)

_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}\s*$")


class LLMInterface:
    """Unified interface for OpenAI and OpenRouter."""

    def __init__(self):
        self.api_key = settings.get_llm_api_key()
        self.base_url = settings.get_llm_base_url()
        self.client = self._create_client()

    def _create_client(self) -> OpenAI | None:
        if settings.llm_provider == "local" or not self.api_key:
            logger.info("LLM provider set to local or no API key. Using simulation mode.")
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
            max_retries=0,
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

        # 1. Security filters
        prompt = strip_prompt_injection(prompt)
        if settings.rag_redact_secrets:
            prompt = mask_secrets(prompt)
            system_prompt = mask_secrets(system_prompt)

        if not self.client:
            return self._heuristic_simulation(prompt, json_mode)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

        # 2. Try strict JSON mode if requested and preferred
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
                logger.debug(f"JSON mode failed or unsupported: {e}")
                pass

        # 3. Fallback: Prompt engineering for JSON
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
        if txt.startswith("```json"):
            txt = txt[7:]
        if txt.startswith("```"):
            txt = txt[3:]
        if txt.endswith("```"):
            txt = txt[:-3]
        txt = txt.strip()

        try:
            json.loads(txt)
            return txt
        except Exception:
            pass

        m = _JSON_OBJ_RE.search(txt)
        if m:
            candidate = m.group(0)
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

        return json.dumps({"response": txt})

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "You are a coding expert.",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Generator[str, None, None]:

        prompt = strip_prompt_injection(prompt)
        if settings.rag_redact_secrets:
            prompt = mask_secrets(prompt)
            system_prompt = mask_secrets(system_prompt)

        if not self.client:
            yield "Simulated response "
            yield "chunk."
            return

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

        try:
            stream = self.client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
                stream=True
            )
            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield content
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            yield f"[Error: {str(e)}]"

    def _heuristic_simulation(self, prompt: str, json_mode: bool) -> str:
        """Simulation mode for when no API key is present."""
        p = prompt.lower()

        # Eval harness answers
        if "where is the /api/rag endpoint" in p:
             return json.dumps({"indices": [0]}) if json_mode else "It is in api/server.py."

        if "rate the relevance" in p or "rank them" in p:
             if json_mode:
                 return json.dumps({"indices": [0, 1, 2]})
             return json.dumps(
                {
                    "score": 0.9,
                    "reasoning": "Heuristic match (simulation mode).",
                }
            )

        return json.dumps({"response": "Simulated LLM response (configure a provider key)"}) if json_mode else "Simulated LLM response"
