"""GroqSTT request shape, against a fake HTTP transport (no network)."""

import httpx

from app.providers.groq_stt import STT_PROMPT, GroqSTT


def stt_with(seen: list[bytes], language: str = "") -> GroqSTT:
    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return httpx.Response(200, json={"text": " Sige po, sa Biyernes. "})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    return GroqSTT(client, "key", "whisper-large-v3-turbo", language)


async def test_detects_the_language_and_hints_taglish_and_doctor_names() -> None:
    seen: list[bytes] = []
    text = await stt_with(seen).transcribe(b"RIFF....")
    assert text == "Sige po, sa Biyernes."
    body = seen[0].decode(errors="ignore")
    assert 'name="language"' not in body  # Whisper detects English or Tagalog itself
    assert STT_PROMPT in body and "Dr. Ana Reyes" in STT_PROMPT


async def test_a_configured_language_is_forced() -> None:
    seen: list[bytes] = []
    await stt_with(seen, language="en").transcribe(b"RIFF....")
    body = seen[0].decode(errors="ignore")
    assert 'name="language"' in body and "\r\n\r\nen\r\n" in body
