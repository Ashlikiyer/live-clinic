import httpx

from app.core.config import Settings
from app.providers.base import Providers
from app.providers.fake import FakeLLM, FakeSTT
from app.providers.groq_llm import GroqLLM
from app.providers.groq_stt import GroqSTT


def build_providers(settings: Settings, client: httpx.AsyncClient) -> Providers:
    if settings.provider == "fake":
        return Providers(stt=FakeSTT(), llm=FakeLLM())
    if not settings.groq_api_key or not settings.llm_model:
        raise RuntimeError("PROVIDER=groq needs GROQ_API_KEY and LLM_MODEL in the environment.")
    return Providers(
        stt=GroqSTT(client, settings.groq_api_key, settings.stt_model),
        llm=GroqLLM(
            client,
            settings.groq_api_key,
            settings.llm_model,
            reasoning_effort=settings.llm_reasoning_effort,
        ),
    )
