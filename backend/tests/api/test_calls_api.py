"""Call detail and transcript endpoints: own calls only, everything else is a 404."""

from fastapi.testclient import TestClient

from app.providers.fake import FakeLLM

from ..call.helpers import new_token, receive_until, start_call


def _finished_call(client: TestClient, llm: FakeLLM) -> tuple[str, str]:
    llm.replies = ["We open at 9 AM."]
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        call_id = start_call(ws)[0]["call_id"]
        ws.send_json({"type": "text.message", "text": "When do you open?", "ts": 1})
        receive_until(ws, "agent.text.done", turn_id=1)
        ws.send_json({"type": "call.end", "reason": "user"})
        receive_until(ws, "call.ended")
    return token, call_id


def test_own_call_detail_and_transcript(client: TestClient, llm: FakeLLM) -> None:
    token, call_id = _finished_call(client, llm)

    detail = client.get(f"/api/calls/{call_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    body = detail.json()
    assert body["outcome"] == "info_only"
    assert [t["role"] for t in body["transcript"]] == ["assistant", "user", "assistant"]

    text = client.get(
        f"/api/calls/{call_id}/transcript.txt", headers={"Authorization": f"Bearer {token}"}
    )
    assert text.status_code == 200
    assert text.headers["content-type"].startswith("text/plain")
    assert "Caller: When do you open?\nMia: We open at 9 AM." in text.text


def test_other_sessions_get_404_and_no_session_gets_401(client: TestClient, llm: FakeLLM) -> None:
    _, call_id = _finished_call(client, llm)
    stranger = new_token(client)
    for path in (f"/api/calls/{call_id}", f"/api/calls/{call_id}/transcript.txt"):
        response = client.get(path, headers={"Authorization": f"Bearer {stranger}"})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    client.cookies.clear()  # the session cookie would otherwise authenticate the request
    anonymous = client.get(f"/api/calls/{call_id}")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "SESSION_EXPIRED"
    assert (
        client.get(
            "/api/calls/not-a-uuid", headers={"Authorization": f"Bearer {stranger}"}
        ).status_code
        == 404
    )


def test_silence_ending_is_recorded(client: TestClient) -> None:
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "call.end", "reason": "silence"})
        ended = receive_until(ws, "call.ended")[-1]
    assert ended["outcome"] == "abandoned"
    assert "silent" in ended["summary"]
