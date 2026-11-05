"""Deterministic providers for tests and offline development (PROVIDER=fake)."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import ErrorCode
from app.providers.base import ChatMessage, LLMChunk, ProviderError, ToolCallRequest

FAKE_AUDIO_PREFIX = b"FAKE:"


def fake_wav(text: str) -> bytes:
    """An "utterance" the fake STT transcribes back to `text`."""
    return FAKE_AUDIO_PREFIX + text.encode()


class FakeSTT:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def transcribe(self, wav: bytes) -> str:
        if self.fail:
            raise ProviderError(ErrorCode.STT_FAILED, "Fake transcription failure.")
        if wav.startswith(FAKE_AUDIO_PREFIX):
            return wav[len(FAKE_AUDIO_PREFIX) :].decode()
        return "Hello?"


# Tool arguments, or a function that builds them from the messages so far (e.g. to reuse a
# slot_start or hold_id returned by an earlier tool).
ToolArgs = dict[str, Any] | Callable[[list[ChatMessage]], dict[str, Any]]


@dataclass
class ToolStep:
    """A scripted LLM round that calls tools (optionally after some text)."""

    calls: list[tuple[str, ToolArgs]]
    text: str = ""


@dataclass
class FakeLLM:
    """Replies with a fixed script, or echoes the caller, streamed word by word.

    Each `stream()` call consumes one step: a string is spoken text; a ToolStep requests tools.
    `calls` records every message list it was given, so tests can inspect tool results.
    """

    replies: list[str | ToolStep] = field(default_factory=list)
    delay_s: float = 0.0
    fail: bool = False
    calls: list[list[ChatMessage]] = field(default_factory=list)
    tools_seen: list[list[dict[str, Any]] | None] = field(default_factory=list)

    async def stream(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMChunk]:
        self.calls.append(list(messages))
        self.tools_seen.append(tools)
        if self.fail:
            raise ProviderError(ErrorCode.LLM_FAILED, "Fake reply failure.")
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        step = self.replies.pop(0) if self.replies else f"You said {last_user}. Anything else?"
        text = step.text if isinstance(step, ToolStep) else step
        for i, word in enumerate(text.split(" ") if text else []):
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            yield word if i == 0 else f" {word}"
        if isinstance(step, ToolStep):
            for n, (name, args) in enumerate(step.calls):
                resolved = args(messages) if callable(args) else args
                yield ToolCallRequest(f"fake_{len(self.calls)}_{n}", name, json.dumps(resolved))


@dataclass
class FakeTTS:
    """Speech for tests: 10 ms of silence per character, in two chunks. Records each request."""

    fail: bool = False
    sample_rate: int = 24_000
    requests: list[str] = field(default_factory=list)

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        self.requests.append(text)
        if self.fail:
            raise ProviderError(ErrorCode.RATE_LIMITED, "Busy right now, try again in a minute.")
        pcm = bytes(2 * self.sample_rate // 100 * len(text))
        half = len(pcm) // 2 - (len(pcm) // 2) % 2
        for chunk in (pcm[:half], pcm[half:]):
            if chunk:
                yield chunk
