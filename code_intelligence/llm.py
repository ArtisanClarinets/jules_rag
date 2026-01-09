from __future__ import annotations

from typing import Optional
import json
import re

from openai import OpenAI

from .config import LLMConfig, load_llm_config


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}\s*$")


class LLMInterface:
    """Small wrapper around OpenAI-compatible chat completions.

    Supports:
    - OpenAI (default)
    - OpenRouter (set LLM_PROVIDER=openrouter + OPENROUTER_API_KEY)

    If no API key is configured, falls back to a simple heuristic simulator so
    the rest of the pipeline can run locally.
    """

    def __init__(self, cfg: Optional[LLMConfig] = None):
        self.cfg = cfg or load_llm_config()

        # Backwards compatibility: previous versions used OPENAI_API_KEY only.
        api_key = self.cfg.provider.api_key
        if api_key:
            headers = {}
            if self.cfg.provider.provider == "openrouter":
                # OpenRouter recommends these headers (optional), see their docs.
                if self.cfg.provider.http_referer:
                    headers["HTTP-Referer"] = self.cfg.provider.http_referer
                if self.cfg.provider.x_title:
                    headers["X-Title"] = self.cfg.provider.x_title

            self.client = OpenAI(
                api_key=api_key,
                base_url=self.cfg.provider.base_url,
                default_headers=headers or None,
            )
        else:
            self.client = None

    def generate_response(self, prompt: str, system_prompt: str = "You are a coding expert.") -> str:
        """Return the model's response text.

        Many callers in this repo expect JSON strings (judges). We *prefer* JSON
        mode, but fall back gracefully when a provider/model doesn't support it.
        """

        if not self.client:
            return self._heuristic_simulation(prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        # Try strict JSON mode first.
        if self.cfg.prefer_json:
            try:
                response = self.client.chat.completions.create(
                    model=self.cfg.model,
                    messages=messages,
                    temperature=self.cfg.temperature,
                    max_tokens=self.cfg.max_tokens,
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content or "{}"
            except Exception:
                # Some models/providers don't support response_format.
                pass

        # Fallback: ask for JSON explicitly and parse best-effort.
        try:
            response = self.client.chat.completions.create(
                model=self.cfg.model,
                messages=messages + [
                    {
                        "role": "system",
                        "content": "Return valid JSON only (no markdown).",
                    }
                ],
                temperature=self.cfg.temperature,
                max_tokens=self.cfg.max_tokens,
            )
            txt = response.choices[0].message.content or "{}"
            # Ensure callers get something parseable.
            return self._coerce_json(txt)
        except Exception as e:
            return json.dumps({"error": str(e), "score": 0.0, "is_valid": False, "reasoning": "LLM Error"})

    def _coerce_json(self, txt: str) -> str:
        txt = txt.strip()
        # Happy path.
        try:
            json.loads(txt)
            return txt
        except Exception:
            pass

        # Try to extract the last JSON object in the response.
        m = _JSON_OBJ_RE.search(txt)
        if m:
            candidate = m.group(0)
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

        # Worst case: wrap as an object.
        return json.dumps({"response": txt})

    def _heuristic_simulation(self, prompt: str) -> str:
        """Heuristic fallback to keep judges functional without a key."""

        p = prompt.lower()
        if "rate the relevance" in p:
            return json.dumps(
                {
                    "score": 0.9,
                    "reasoning": "Heuristic match (simulation mode). Set LLM_PROVIDER + API key for real inference.",
                }
            )
        if "check for contradictions" in p:
            return json.dumps({"consistent": True, "issues": []})
        return json.dumps({"response": "Simulated LLM response (configure a provider key for real inference)"})
