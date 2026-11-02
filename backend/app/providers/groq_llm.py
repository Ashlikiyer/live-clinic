"""Groq chat completions (streaming) over plain httpx."""

import json
from collections.abc import AsyncIterator

import httpx

from app.core.errors import ErrorCode
from app.providers.base import ChatMessage, ProviderError
from app.providers.groq_stt import GROQ_BASE_URL, error_for


class GroqLLM:
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        *,
        temperature: float = 0.5,
        max_tokens: int = 220,
        reasoning_effort: str = "",
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._reasoning_effort = reasoning_effort

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        body: dict[str, object] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        try:
            async with self._client.stream(
                "POST",
                f"{GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
                timeout=httpx.Timeout(20.0, connect=5.0),
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise error_for(response, ErrorCode.LLM_FAILED, "Reply")
                async for line in response.aiter_lines():
                    delta = parse_sse_delta(line)
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise ProviderError(ErrorCode.LLM_FAILED, f"Reply failed: {exc}") from exc


def parse_sse_delta(line: str) -> str | None:
    """Text delta from one server-sent-events line of an OpenAI-style stream, if any."""
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        chunk = json.loads(payload)
    except json.JSONDecodeError:
        return None
    choices = chunk.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("delta") or {}).get("content")
    return content if isinstance(content, str) and content else None
