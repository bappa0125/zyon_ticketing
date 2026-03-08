"""OpenRouter LLM Gateway - streaming, model switching."""
import json
from typing import AsyncGenerator, Optional

import httpx
from openai import AsyncOpenAI

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMGateway:
    """Gateway for OpenRouter API - supports streaming and model switching."""

    def __init__(self):
        config = get_config()
        self.api_key = config["settings"].openrouter_api_key
        self.base_url = config["openrouter"].get("base_url", "https://openrouter.ai/api/v1")
        self.model = config["settings"].openrouter_model or config["openrouter"].get("model", "openai/gpt-3.5-turbo")
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60.0,
            )
        return self._client

    def set_model(self, model: str) -> None:
        """Switch to a different model."""
        self.model = model

    async def _chat_with_web_search_direct(self, model: str, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Direct HTTP call to OpenRouter. Perplexity Sonar does web search natively."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": 800,
        }
        if "perplexity" not in model.lower():
            payload["plugins"] = [{"id": "web", "max_results": 10, "engine": "exa"}]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://zyon-chatbot.local",
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error("OpenRouter web search failed", status=resp.status_code, body=err.decode()[:500])
                    yield json.dumps({"error": f"OpenRouter error {resp.status_code}: {err.decode()[:200]}"})
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        choices = obj.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def chat_completion(
        self,
        messages: list[dict],
        stream: bool = True,
        use_web_search: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Send messages to OpenRouter. use_web_search uses direct HTTP with plugins."""
        if not self.api_key:
            yield json.dumps({"error": "OPENROUTER_API_KEY not set"})
            return

        model = self.model
        if use_web_search:
            raw = (get_config().get("openrouter") or {}).get("web_search_model") or ""
            if raw and "perplexity" in raw.lower() and "openrouter" not in raw.lower():
                model = raw
            else:
                model = "perplexity/sonar"
            if "openrouter" in model.lower() or ":online" in model or "/fr" in model:
                model = "perplexity/sonar"
            logger.info("web_search_model", model=model)
            try:
                async for chunk in self._chat_with_web_search_direct(model, messages):
                    yield chunk
                return
            except Exception as e:
                logger.error("Web search request failed", error=str(e))
                yield json.dumps({"error": str(e)})
                return

        try:
            client = self._get_client()
            stream_obj = await client.chat.completions.create(
                model=model, messages=messages, stream=stream
            )
            if stream:
                async for chunk in stream_obj:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta and getattr(delta, "content", None):
                            yield delta.content
            else:
                if stream_obj.choices and len(stream_obj.choices) > 0 and stream_obj.choices[0].message.content:
                    yield stream_obj.choices[0].message.content
        except Exception as e:
            logger.error("LLM request failed", error=str(e))
            yield json.dumps({"error": str(e)})
