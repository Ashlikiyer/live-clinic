from fastapi.testclient import TestClient

from app.providers.fake import FakeLLM
from app.routers.health import get_database_check


def _override(client: TestClient, ok: bool) -> None:
    async def check() -> bool:
        return ok

    client.app.dependency_overrides[get_database_check] = lambda: check  # type: ignore[attr-defined]


def test_health_ok_when_database_answers(client: TestClient) -> None:
    _override(client, True)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "llm": "ok", "busy_seconds": 0}


def test_health_says_when_mias_line_is_busy(client: TestClient, llm: FakeLLM) -> None:
    _override(client, True)
    llm.busy_s = 5  # a short limit is waited out: not busy
    assert client.get("/api/health").json()["llm"] == "ok"
    llm.busy_s = 90
    body = client.get("/api/health").json()
    assert body["llm"] == "busy" and body["busy_seconds"] == 90


def test_health_503_when_database_down(client: TestClient) -> None:
    _override(client, False)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


def test_unknown_route_uses_error_format(client: TestClient) -> None:
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
