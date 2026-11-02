"""Deterministic providers for tests and offline development (PROVIDER=fake)."""

import asyncio
from collections.abc import AsyncIterator

from app.core.errors import ErrorCode
from app.providers.base import ChatMessage, ProviderError

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


class FakeLLM:
    """Replies with a fixed script, or echoes the caller, streamed word by word."""

    def __init__(
        self,
        replies: list[str] | None = None,
        delay_s: float = 0.0,
        fail: bool = False,
    ) -> None:
        self.replies = list(replies or [])
        self.delay_s = delay_s
        self.fail = fail
        self.calls: list[list[ChatMessage]] = []

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append(list(messages))
        if self.fail:
            raise ProviderError(ErrorCode.LLM_FAILED, "Fake reply failure.")
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        reply = self.replies.pop(0) if self.replies else f"You said {last_user}. Anything else?"
        for i, word in enumerate(reply.split(" ")):
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            yield word if i == 0 else f" {word}"
