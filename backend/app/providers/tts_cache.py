"""Keeps the speech for Mia's fixed lines, so each costs one Groq request, ever (per process).

The free tier allows 100 speech requests a day; the greeting alone would otherwise use one
per call.
"""

from collections.abc import AsyncIterator

from app.agent.prompt import (
    ANYTHING_ELSE_LINE,
    FILLER_LINE,
    GIVE_UP_LINE,
    GOODBYE_LINE,
    GREETING,
    LLM_RECOVERY_LINE,
    NUDGE_LINE,
    RECONNECT_LINE,
    SILENCE_GOODBYE_LINE,
    STT_RECOVERY_LINE,
    TIME_LIMIT_LINE,
)
from app.call.emergency import EMERGENCY_REPLY
from app.providers.base import TTSProvider

FIXED_LINES = frozenset(
    {
        GREETING,
        RECONNECT_LINE,
        STT_RECOVERY_LINE,
        LLM_RECOVERY_LINE,
        ANYTHING_ELSE_LINE,
        GOODBYE_LINE,
        GIVE_UP_LINE,
        TIME_LIMIT_LINE,
        EMERGENCY_REPLY,
        FILLER_LINE,
        NUDGE_LINE,
        SILENCE_GOODBYE_LINE,
    }
)


class CachedTTS:
    """Wraps a TTS provider; fixed lines are synthesized once and replayed from memory."""

    def __init__(self, inner: TTSProvider, cacheable: frozenset[str] = FIXED_LINES) -> None:
        self._inner = inner
        self._cacheable = cacheable
        self._cache: dict[str, list[bytes]] = {}

    @property
    def sample_rate(self) -> int:
        return self._inner.sample_rate

    def is_cached(self, text: str) -> bool:
        return text in self._cache

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        if (hit := self._cache.get(text)) is not None:
            for chunk in hit:
                yield chunk
            return
        chunks: list[bytes] = []
        async for chunk in self._inner.stream(text):
            chunks.append(chunk)
            yield chunk
        # Only a complete synthesis is kept (a cancelled stream never gets here).
        if text in self._cacheable:
            self._cache[text] = chunks
