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
            )
        return self._client

    def set_model(self, model: str) -> None:
        """Switch to a different model."""
        self.model = model

    async def chat_completion(
        self,
        messages: list[dict],
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Send messages to OpenRouter and stream the response."""
        if not self.api_key:
            yield json.dumps({"error": "OPENROUTER_API_KEY not set"})
            return

        try:
            client = self._get_client()
            stream_obj = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=stream,
            )

            if stream:
                async for chunk in stream_obj:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            else:
                if stream_obj.choices and stream_obj.choices[0].message.content:
                    yield stream_obj.choices[0].message.content

        except Exception as e:
            logger.error("LLM request failed", error=str(e))
            yield json.dumps({"error": str(e)})
