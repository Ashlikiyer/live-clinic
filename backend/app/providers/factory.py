import httpx

from app.core.config import Settings
from app.providers.base import Providers
from app.providers.fake import FakeLLM, FakeSTT, FakeTTS
from app.providers.groq_llm import GroqLLM, parse_model_list
from app.providers.groq_stt import GroqSTT
from app.providers.groq_tts import GroqTTS
from app.providers.tts_cache import CachedTTS


def build_providers(settings: Settings, client: httpx.AsyncClient) -> Providers:
    if settings.provider == "fake":
        return Providers(stt=FakeSTT(), llm=FakeLLM(), tts=CachedTTS(FakeTTS()))
    if not settings.groq_api_key or not settings.llm_model:
        raise RuntimeError("PROVIDER=groq needs GROQ_API_KEY and LLM_MODEL in the environment.")
    return Providers(
        stt=GroqSTT(client, settings.groq_api_key, settings.stt_model),
        llm=GroqLLM(
            client,
            settings.groq_api_key,
            settings.llm_model,
            reasoning_effort=settings.llm_reasoning_effort,
            fallbacks=parse_model_list(settings.llm_fallback_models),
        ),
        tts=CachedTTS(
            GroqTTS(client, settings.groq_api_key, settings.tts_model, settings.tts_voice)
        ),
    )
