import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def generate_text(prompt: str, system_prompt: str = "You are a helpful assistant.", temperature: float = 0.0) -> str:
    """
    Generate text using an LLM (OpenAI compatible).
    """
    # Try OpenRouter first, then OpenAI, then generic LLM env vars
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") if os.getenv("OPENROUTER_API_KEY") else \
               os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") if os.getenv("OPENAI_API_KEY") else \
               os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        logger.warning("No LLM API key found. Returning simulation response.")
        return f"Simulated response to: {prompt[:50]}..."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # OpenRouter specific headers
    if "openrouter.ai" in base_url:
        if os.getenv("OPENROUTER_HTTP_REFERER"):
            headers["HTTP-Referer"] = os.getenv("OPENROUTER_HTTP_REFERER")
        if os.getenv("OPENROUTER_X_TITLE"):
            headers["X-Title"] = os.getenv("OPENROUTER_X_TITLE")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return f"Error generating text: {e}"

def generate_text_sync(prompt: str, system_prompt: str = "You are a helpful assistant.", temperature: float = 0.0) -> str:
    """
    Synchronous version of generate_text.
    """
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") if os.getenv("OPENROUTER_API_KEY") else \
               os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") if os.getenv("OPENAI_API_KEY") else \
               os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        logger.warning("No LLM API key found. Returning simulation response.")
        return f"Simulated response to: {prompt[:50]}..."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    if "openrouter.ai" in base_url:
        if os.getenv("OPENROUTER_HTTP_REFERER"):
            headers["HTTP-Referer"] = os.getenv("OPENROUTER_HTTP_REFERER")
        if os.getenv("OPENROUTER_X_TITLE"):
            headers["X-Title"] = os.getenv("OPENROUTER_X_TITLE")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return f"Error generating text: {e}"
