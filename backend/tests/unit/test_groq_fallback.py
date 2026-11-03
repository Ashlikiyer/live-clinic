"""GroqLLM model fallback, against a fake HTTP transport (no network)."""

import json

import httpx
import pytest

from app.core.errors import ErrorCode
from app.providers.base import ChatMessage, ProviderError
from app.providers.groq_llm import (
    REASONING_TOKEN_ALLOWANCE,
    GroqLLM,
    ModelChoice,
    parse_model_list,
)


def sse(text: str) -> bytes:
    chunk = {"choices": [{"delta": {"content": text}}]}
    return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()


class FakeGroq:
    """Rate limits the models in `limited`; answers with the model's name otherwise."""

    def __init__(self, limited: set[str]) -> None:
        self.limited = limited
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if body["model"] in self.limited:
            return httpx.Response(429, headers={"retry-after": "30"}, json={"error": {}})
        return httpx.Response(200, content=sse(f"from {body['model']}"))


async def reply(llm: GroqLLM) -> str:
    return "".join([c async for c in llm.stream([ChatMessage("user", "hi")]) if isinstance(c, str)])


def make(fake: FakeGroq) -> GroqLLM:
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    return GroqLLM(
        client,
        "key",
        "qwen",
        reasoning_effort="none",
        fallbacks=[ModelChoice("oss-120b", "low"), ModelChoice("oss-20b", "low")],
    )


async def test_uses_the_primary_model_when_it_is_free() -> None:
    fake = FakeGroq(limited=set())
    assert await reply(make(fake)) == "from qwen"
    assert fake.requests[0]["reasoning_effort"] == "none"


async def test_falls_back_on_rate_limit_and_skips_the_limited_model_afterwards() -> None:
    fake = FakeGroq(limited={"qwen"})
    llm = make(fake)
    assert await reply(llm) == "from oss-120b"
    assert fake.requests[1]["reasoning_effort"] == "low"
    # The reasoning fallback gets room to reason before its short spoken reply.
    assert fake.requests[0]["max_tokens"] == 160
    assert fake.requests[1]["max_tokens"] == 160 + REASONING_TOKEN_ALLOWANCE
    assert await reply(llm) == "from oss-120b"
    # The second call didn't waste a request on the cooling-down model.
    assert [r["model"] for r in fake.requests] == ["qwen", "oss-120b", "oss-120b"]


async def test_all_models_limited_raises_rate_limited() -> None:
    fake = FakeGroq(limited={"qwen", "oss-120b", "oss-20b"})
    with pytest.raises(ProviderError) as exc:
        await reply(make(fake))
    assert exc.value.code == ErrorCode.RATE_LIMITED


async def test_other_errors_do_not_fall_back() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    llm = GroqLLM(
        httpx.AsyncClient(transport=httpx.MockTransport(broken)),
        "k",
        "qwen",
        fallbacks=[ModelChoice("oss-120b")],
    )
    with pytest.raises(ProviderError) as exc:
        await reply(llm)
    assert exc.value.code == ErrorCode.LLM_FAILED


def test_parse_model_list() -> None:
    assert parse_model_list(" openai/gpt-oss-120b:low, openai/gpt-oss-20b ,") == [
        ModelChoice("openai/gpt-oss-120b", "low"),
        ModelChoice("openai/gpt-oss-20b", ""),
    ]
    assert parse_model_list("") == []


async def test_waits_briefly_when_every_model_is_about_to_free_up() -> None:
    class Brief(FakeGroq):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.requests.append(body)
            if len(self.requests) <= 3:  # every model limited once, for a moment
                return httpx.Response(429, headers={"retry-after": "0.05"}, json={})
            return httpx.Response(200, content=sse(f"from {body['model']}"))

    fake = Brief(limited=set())
    assert await reply(make(fake)) == "from qwen"
    assert len(fake.requests) == 4
