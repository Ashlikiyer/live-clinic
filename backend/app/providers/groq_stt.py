"""Groq Whisper speech-to-text over plain httpx."""

import httpx

from app.core.errors import ErrorCode
from app.providers.base import ProviderError

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Whisper's prompt is a "previous text" hint: a little Taglish and the clinic's names make it
# expect code-switching and spell the doctors right ("Ana", not "Anna").
STT_PROMPT = (
    "Bayview Family Clinic. Hello po, gusto ko pong mag-book ng appointment. Yes, okay lang po. "
    "Dr. Ana Reyes, Dr. Paolo Cruz, Dr. Lea Santos."
)


def error_for(response: httpx.Response, default: ErrorCode, what: str) -> ProviderError:
    if response.status_code == 429:
        return ProviderError(
            ErrorCode.RATE_LIMITED,
            "Busy right now, try again in a minute.",
            details={"retry_after": response.headers.get("retry-after", "")},
        )
    retryable = response.status_code >= 500
    return ProviderError(default, f"{what} failed ({response.status_code}).", retryable=retryable)


class GroqSTT:
    def __init__(
        self, client: httpx.AsyncClient, api_key: str, model: str, language: str = ""
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        # "" lets Whisper detect English or Tagalog per utterance (callers mix both).
        self._language = language

    async def transcribe(self, wav: bytes) -> str:
        data = {
            "model": self._model,
            "temperature": "0",
            "response_format": "json",
            "prompt": STT_PROMPT,
        }
        if self._language:
            data["language"] = self._language
        try:
            response = await self._client.post(
                f"{GROQ_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": ("utterance.wav", wav, "audio/wav")},
                data=data,
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(ErrorCode.STT_FAILED, f"Transcription failed: {exc}") from exc
        if response.status_code != 200:
            raise error_for(response, ErrorCode.STT_FAILED, "Transcription")
        return str(response.json().get("text", "")).strip()
