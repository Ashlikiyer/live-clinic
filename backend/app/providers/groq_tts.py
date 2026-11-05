"""Groq text-to-speech (Orpheus) over plain httpx, streamed as raw 16-bit PCM.

Groq streams a WAV file whose header announces a placeholder length, so the PCM is read past
the header as it arrives (WavStreamParser) and passed on in small chunks.
"""

import struct
from collections.abc import AsyncIterator

import httpx

from app.core.errors import ErrorCode
from app.providers.base import ProviderError
from app.providers.groq_stt import GROQ_BASE_URL, error_for

# Bytes per streamed chunk: 0.25 s of 24 kHz 16-bit mono.
CHUNK_BYTES = 12_000


class WavStreamParser:
    """Turns a streamed WAV file into its PCM samples. Pure, no I/O.

    Feed bytes as they arrive; `feed` returns the PCM after the `data` chunk header, always an
    even number of bytes (whole 16-bit samples). `sample_rate` is known once `fmt ` is read.
    """

    def __init__(self) -> None:
        self._head = b""
        self._in_data = False
        self._carry = b""
        self.sample_rate: int | None = None

    def feed(self, data: bytes) -> bytes:
        if not self._in_data:
            self._head += data
            pcm = self._read_header()
            if pcm is None:
                return b""
            data = pcm
        data = self._carry + data
        whole = len(data) - len(data) % 2
        self._carry = data[whole:]
        return data[:whole]

    def _read_header(self) -> bytes | None:
        """Walk the RIFF chunks; return the bytes after the data chunk header, or None."""
        head = self._head
        if len(head) < 12:
            return None
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise ValueError("Not a WAV stream.")
        offset = 12
        while len(head) >= offset + 8:
            chunk_id = head[offset : offset + 4]
            (size,) = struct.unpack("<I", head[offset + 4 : offset + 8])
            if chunk_id == b"data":
                self._in_data = True
                return head[offset + 8 :]
            if len(head) < offset + 8 + size:
                return None  # chunk body not here yet
            if chunk_id == b"fmt " and size >= 16:
                channels, rate = struct.unpack("<HI", head[offset + 10 : offset + 16])
                bits = struct.unpack("<H", head[offset + 22 : offset + 24])[0]
                if channels != 1 or bits != 16:
                    raise ValueError("Expected 16-bit mono audio.")
                self.sample_rate = rate
            offset += 8 + size + size % 2  # chunks are word-aligned
        return None


class GroqTTS:
    """Orpheus voices on Groq. Free tier: 100 requests a day, 1,200 characters a minute."""

    def __init__(self, client: httpx.AsyncClient, api_key: str, model: str, voice: str) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self.sample_rate = 24_000

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        parser = WavStreamParser()
        pending = b""
        try:
            async with self._client.stream(
                "POST",
                f"{GROQ_BASE_URL}/audio/speech",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "voice": self._voice,
                    "input": text,
                    "response_format": "wav",
                },
                timeout=httpx.Timeout(30.0, connect=5.0),
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise error_for(response, ErrorCode.TTS_FAILED, "Speech")
                async for data in response.aiter_bytes():
                    pending += parser.feed(data)
                    if parser.sample_rate:
                        self.sample_rate = parser.sample_rate
                    while len(pending) >= CHUNK_BYTES:
                        yield pending[:CHUNK_BYTES]
                        pending = pending[CHUNK_BYTES:]
        except httpx.HTTPError as exc:
            raise ProviderError(ErrorCode.TTS_FAILED, f"Speech failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(ErrorCode.TTS_FAILED, f"Speech failed: {exc}") from exc
        if pending:
            yield pending
