from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.base import Providers
from app.providers.fake import FakeLLM, FakeSTT
from app.repositories.calls import MemoryCallStore


@pytest.fixture
def store() -> MemoryCallStore:
    return MemoryCallStore()


@pytest.fixture
def stt() -> FakeSTT:
    return FakeSTT()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(store: MemoryCallStore, stt: FakeSTT, llm: FakeLLM) -> Iterator[TestClient]:
    """App wired to an in-memory store and deterministic fake providers."""
    with TestClient(create_app(store=store, providers=Providers(stt=stt, llm=llm))) as c:
        yield c
