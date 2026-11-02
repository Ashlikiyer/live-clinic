"""Interfaces for speech-to-text and LLM providers. Everything external goes through these."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.core.errors import ErrorCode

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCallRequest:
    """The LLM asked to run a tool. `arguments` is the raw JSON string it produced."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    # Set on assistant messages that requested tools.
    tool_calls: tuple[ToolCallRequest, ...] = ()
    # Set on role="tool" messages: which request this result answers.
    tool_call_id: str | None = None


# A streamed LLM reply is text deltas, then any tool calls once their arguments are complete.
LLMChunk = str | ToolCallRequest


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
    def stream(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMChunk]:
        """Stream the assistant reply: text deltas, then complete tool calls."""
        ...


async def complete_text(llm: LLMProvider, messages: list[ChatMessage]) -> str:
    """Collect a short, tool-free reply (e.g. a one-word yes/no check)."""
    parts = [chunk async for chunk in llm.stream(messages) if isinstance(chunk, str)]
    return "".join(parts)


@dataclass(frozen=True)
class Providers:
    stt: STTProvider
    llm: LLMProvider
