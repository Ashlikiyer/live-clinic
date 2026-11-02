from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.repositories.calls import MemoryCallStore


def test_creates_session_with_token_and_cookie(client: TestClient, store: MemoryCallStore) -> None:
    response = client.post("/api/sessions")
    assert response.status_code == 201
    body = response.json()
    assert len(body["session_token"]) >= 40
    assert response.cookies.get("session_token") == body["session_token"]
    stored = next(iter(store.sessions.values()))
    # Only hashes are stored, never the token or the IP.
    assert body["session_token"] not in stored.values()
    assert stored["ip_hash"] != "testclient"


def test_sessions_are_rate_limited_per_ip(client: TestClient) -> None:
    limit = get_settings().sessions_per_ip_per_day
    for _ in range(limit):
        assert client.post("/api/sessions").status_code == 201
    response = client.post("/api/sessions")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
