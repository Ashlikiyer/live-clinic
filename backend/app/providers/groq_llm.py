"""Groq chat completions (streaming, with tool calling) over plain httpx."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.errors import ErrorCode
from app.providers.base import ChatMessage, LLMChunk, ProviderError, ToolCallRequest
from app.providers.groq_stt import GROQ_BASE_URL, error_for


def message_payload(m: ChatMessage) -> dict[str, Any]:
    """OpenAI-style message dict, including tool requests and tool results."""
    payload: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        payload["content"] = m.content or None
        payload["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in m.tool_calls
        ]
    if m.tool_call_id is not None:
        payload["tool_call_id"] = m.tool_call_id
    return payload


@dataclass
class _PartialCall:
    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)


class StreamParser:
    """Turns OpenAI-style SSE lines into text deltas and complete tool calls.

    Tool-call fragments are merged by `index` and released once the stream finishes, because
    arguments may arrive in pieces.
    """

    def __init__(self) -> None:
        self._calls: dict[int, _PartialCall] = {}

    def feed(self, line: str) -> list[LLMChunk]:
        chunk = _parse_data_line(line)
        if chunk is None:
            return []
        choices = chunk.get("choices") or []
        if not choices:
            return []
        delta = choices[0].get("delta") or {}
        out: list[LLMChunk] = []
        content = delta.get("content")
        if isinstance(content, str) and content:
            out.append(content)
        for fragment in delta.get("tool_calls") or []:
            partial = self._calls.setdefault(int(fragment.get("index", 0)), _PartialCall())
            partial.id = fragment.get("id") or partial.id
            function = fragment.get("function") or {}
            partial.name = function.get("name") or partial.name
            if function.get("arguments"):
                partial.arguments.append(function["arguments"])
        return out

    def finish(self) -> list[ToolCallRequest]:
        calls = [
            ToolCallRequest(p.id or f"call_{i}", p.name, "".join(p.arguments) or "{}")
            for i, p in sorted(self._calls.items())
            if p.name
        ]
        self._calls.clear()
        return calls


def _parse_data_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_sse_delta(line: str) -> str | None:
    """Text delta from one server-sent-events line of an OpenAI-style stream, if any."""
    texts = [c for c in StreamParser().feed(line) if isinstance(c, str)]
    return texts[0] if texts else None


@dataclass(frozen=True)
class ModelChoice:
    name: str
    # Groq reasoning_effort for reasoning models ("none" for Qwen 3, "low" for gpt-oss).
    reasoning_effort: str = ""


def parse_model_list(spec: str) -> list[ModelChoice]:
    """'openai/gpt-oss-120b:low, openai/gpt-oss-20b:low' -> model choices."""
    choices = []
    for item in spec.split(","):
        name, _, effort = item.strip().partition(":")
        if name:
            choices.append(ModelChoice(name, effort))
    return choices


DEFAULT_COOLDOWN_S = 20.0
# If every model is rate limited but one frees up within this many seconds, wait for it rather
# than failing the turn (a short pause beats "Sorry, I had trouble").
MAX_WAIT_S = 4.0

log = logging.getLogger(__name__)


class GroqLLM:
    """Streams from the first model that isn't rate limited.

    The free tier limits tokens per minute per model, so on a rate limit (before anything was
    streamed) the same request goes to the next model, and the limited one is skipped until
    Groq's retry-after has passed.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        *,
        temperature: float = 0.4,
        max_tokens: int = 160,  # 1-3 spoken sentences; a lower cap also eases free-tier limits
        reasoning_effort: str = "",
        fallbacks: list[ModelChoice] | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._models = [ModelChoice(model, reasoning_effort), *(fallbacks or [])]
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._cooldown_until: dict[str, float] = {}

    def _order(self) -> list[ModelChoice]:
        now = time.monotonic()
        ready = [m for m in self._models if self._cooldown_until.get(m.name, 0) <= now]
        return ready or self._models[:1]

    async def stream(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMChunk]:
        try:
            async for chunk in self._stream_any(messages, tools):
                yield chunk
            return
        except ProviderError as exc:
            if exc.code != ErrorCode.RATE_LIMITED or exc.details.get("started"):
                raise
            wait = min(self._cooldown_until.values(), default=0) - time.monotonic()
            if wait > MAX_WAIT_S:
                raise
        await asyncio.sleep(max(0.0, wait))
        async for chunk in self._stream_any(messages, tools):
            yield chunk

    async def _stream_any(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None
    ) -> AsyncIterator[LLMChunk]:
        last_error: ProviderError | None = None
        for choice in self._order():
            started = False
            try:
                async for chunk in self._stream_one(choice, messages, tools):
                    started = True
                    yield chunk
                return
            except ProviderError as exc:
                if started:
                    exc.details["started"] = "1"
                if exc.code != ErrorCode.RATE_LIMITED or started:
                    raise
                retry = exc.details.get("retry_after", "")
                wait = float(retry) if retry.replace(".", "", 1).isdigit() else DEFAULT_COOLDOWN_S
                self._cooldown_until[choice.name] = time.monotonic() + wait
                log.warning("LLM %s rate limited for %.0fs; trying the next", choice.name, wait)
                last_error = exc
        assert last_error is not None
        raise last_error

    async def _stream_one(
        self,
        choice: ModelChoice,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[LLMChunk]:
        body: dict[str, Any] = {
            "model": choice.name,
            "messages": [message_payload(m) for m in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if choice.reasoning_effort:
            body["reasoning_effort"] = choice.reasoning_effort
        parser = StreamParser()
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
                    for chunk in parser.feed(line):
                        yield chunk
        except httpx.HTTPError as exc:
            raise ProviderError(ErrorCode.LLM_FAILED, f"Reply failed: {exc}") from exc
        for call in parser.finish():
            yield call
