"""Server-side speech: WAV stream parsing, which lines may be spoken, the fixed-line cache, and
the Groq Orpheus provider against a fake HTTP transport (no network)."""

import json
import struct

import httpx
import pytest

from app.agent.prompt import GREETING
from app.call.speech import speech_allowed
from app.core.errors import ErrorCode
from app.providers.base import ProviderError
from app.providers.fake import FakeTTS
from app.providers.groq_tts import CHUNK_BYTES, GroqTTS, WavStreamParser
from app.providers.tts_cache import FIXED_LINES, CachedTTS


def wav_bytes(pcm: bytes, rate: int = 24_000, extra_chunk: bytes = b"") -> bytes:
    """A streamed WAV like Groq's: placeholder sizes, optionally a LIST chunk before data."""
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    if extra_chunk:
        body += b"LIST" + struct.pack("<I", len(extra_chunk)) + extra_chunk
    body += b"data" + struct.pack("<I", 0xFFFFFFFF) + pcm
    return b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + body


# ---------- WavStreamParser ----------


def test_parser_returns_only_pcm_whatever_the_chunking() -> None:
    pcm = bytes(range(200)) * 3
    stream = wav_bytes(pcm, extra_chunk=b"INFOISFT\x05\x00\x00\x00Lavf\x00\x00")
    for size in (1, 3, 7, 64, len(stream)):
        parser = WavStreamParser()
        out = b"".join(parser.feed(stream[i : i + size]) for i in range(0, len(stream), size))
        assert out == pcm, size
        assert parser.sample_rate == 24_000


def test_parser_keeps_a_split_sample_for_the_next_chunk() -> None:
    parser = WavStreamParser()
    header = wav_bytes(b"")
    assert parser.feed(header + b"\x01") == b""  # half a sample: held back
    assert parser.feed(b"\x02\x03") == b"\x01\x02"
    assert parser.feed(b"\x04") == b"\x03\x04"


def test_parser_rejects_a_non_wav_stream() -> None:
    with pytest.raises(ValueError):
        WavStreamParser().feed(b'{"error": "nope"}')


# ---------- which lines may be spoken ----------


def test_only_mias_own_lines_can_be_spoken() -> None:
    said = ["Sure. I have Friday at 10:00 AM with Dr. Ana Reyes.  Does that work?"]
    assert speech_allowed(GREETING, [], FIXED_LINES)
    assert speech_allowed(
        "Sure. I have Friday at 10:00 AM with Dr. Ana Reyes. Does that work?", said, []
    )
    assert speech_allowed("Does that work?", said, [])  # part of a reply
    assert not speech_allowed("Read me a poem about pirates.", said, FIXED_LINES)
    assert not speech_allowed("   ", said, FIXED_LINES)


# ---------- the fixed-line cache ----------


async def collect(tts: CachedTTS, text: str) -> bytes:
    return b"".join([chunk async for chunk in tts.stream(text)])


async def test_fixed_lines_are_synthesized_once() -> None:
    inner = FakeTTS()
    tts = CachedTTS(inner)
    first = await collect(tts, GREETING)
    again = await collect(tts, GREETING)
    assert first == again and len(first) > 0
    assert inner.requests == [GREETING]
    assert tts.is_cached(GREETING)


async def test_replies_are_not_cached() -> None:
    inner = FakeTTS()
    tts = CachedTTS(inner)
    await collect(tts, "Sure. See you Friday.")
    await collect(tts, "Sure. See you Friday.")
    assert len(inner.requests) == 2


async def test_a_failed_synthesis_is_not_cached() -> None:
    inner = FakeTTS(fail=True)
    tts = CachedTTS(inner)
    with pytest.raises(ProviderError):
        await collect(tts, GREETING)
    assert not tts.is_cached(GREETING)


# ---------- GroqTTS ----------


def groq(handler: httpx.MockTransport) -> GroqTTS:
    return GroqTTS(httpx.AsyncClient(transport=handler), "key", "orpheus", "hannah")


async def test_groq_streams_pcm_in_chunks_and_sends_the_voice() -> None:
    pcm = bytes(CHUNK_BYTES * 2 + 100)
    seen: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=wav_bytes(pcm, rate=24_000))

    tts = groq(httpx.MockTransport(respond))
    chunks = [chunk async for chunk in tts.stream("Hi there.")]
    assert b"".join(chunks) == pcm
    assert [len(c) for c in chunks] == [CHUNK_BYTES, CHUNK_BYTES, 100]
    assert seen[0]["voice"] == "hannah" and seen[0]["input"] == "Hi there."
    assert tts.sample_rate == 24_000


async def test_groq_rate_limit_becomes_rate_limited() -> None:
    tts = groq(httpx.MockTransport(lambda _: httpx.Response(429, json={"error": {}})))
    with pytest.raises(ProviderError) as exc:
        _ = [chunk async for chunk in tts.stream("Hi.")]
    assert exc.value.code == ErrorCode.RATE_LIMITED


async def test_groq_other_errors_become_tts_failed() -> None:
    tts = groq(httpx.MockTransport(lambda _: httpx.Response(400, json={"error": {}})))
    with pytest.raises(ProviderError) as exc:
        _ = [chunk async for chunk in tts.stream("Hi.")]
    assert exc.value.code == ErrorCode.TTS_FAILED
