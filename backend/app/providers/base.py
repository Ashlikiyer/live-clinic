"""Interfaces for speech-to-text and LLM providers. Everything external goes through these."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.core.errors import ErrorCode

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass
class ProviderError(Exception):
    """A provider call failed. `code` maps straight onto the WebSocket `error` event."""

    code: ErrorCode
    message: str
    retryable: bool = True
    details: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class STTProvider(Protocol):
    async def transcribe(self, wav: bytes) -> str:
        """Return the transcript of a 16 kHz mono WAV utterance ("" if nothing was said)."""
        ...


class LLMProvider(Protocol):
    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Stream the assistant reply as text deltas."""
        ...


@dataclass(frozen=True)
class Providers:
    stt: STTProvider
    llm: LLMProvider
