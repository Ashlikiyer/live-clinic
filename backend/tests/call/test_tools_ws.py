"""Agent tools over a real call: fake LLM script in, UI events and database rows out.

These use Postgres (the booking tools need it) and are skipped when it isn't reachable.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.prompt import GIVE_UP_LINE, GOODBYE_LINE
from app.call.session import ToolDeps
from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import (
    Doctor,
    SandboxAppointment,
    SeedAppointment,
    SeedPatient,
    ToolCall,
    Turn,
)
from app.db.session import check_database, get_engine, get_sessionmaker
from app.main import create_app
from app.providers.base import ChatMessage, LLMChunk, ProviderError, Providers
from app.providers.fake import FakeLLM, FakeSTT, ToolStep
from app.repositories.booking import BookingRepository
from app.repositories.calls import SqlCallStore
from app.repositories.clinic import ClinicInfoRepository
from seed.__main__ import seed

from .helpers import Event, new_token, receive_until, start_call, text_of

TZ = ZoneInfo("Asia/Manila")


def fresh_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """No pooling: the test client runs its own event loop, and pooled asyncpg connections
    can't move between loops."""
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _prepare_database() -> bool:
    if not await check_database():
        return False
    async with get_sessionmaker()() as db:
        if not await db.scalar(select(func.count()).select_from(Doctor)):
            await seed(db)
    await get_engine().dispose()
    return True


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def sql_client(llm: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    if not asyncio.run(_prepare_database()):
        pytest.skip("Postgres not reachable at DATABASE_URL")
    # Test runs share one IP; lift the per-IP demo limits.
    monkeypatch.setattr(get_settings(), "calls_per_ip_per_day", 100_000)
    monkeypatch.setattr(get_settings(), "sessions_per_ip_per_day", 100_000)
    sessionmaker = fresh_sessionmaker()
    app = create_app(
        store=SqlCallStore(sessionmaker),
        providers=Providers(stt=FakeSTT(), llm=llm),
        tools=ToolDeps(BookingRepository(sessionmaker, TZ), ClinicInfoRepository(sessionmaker)),
    )
    with TestClient(app) as client:
        yield client


# ---------- helpers to build tool args from earlier tool results ----------


def last_tool_result(messages: list[ChatMessage], key: str) -> dict[str, Any]:
    for m in reversed(messages):
        if m.role == "tool":
            data = json.loads(m.content)
            if key in data:
                return data  # type: ignore[no-any-return]
    raise AssertionError(f"no earlier tool result with {key!r}")


def first_slot(messages: list[ChatMessage]) -> dict[str, Any]:
    slot = last_tool_result(messages, "slots")["slots"][0]
    return {"slot_start": slot["slot_start"], "doctor_id": slot["doctor_id"]}


def held(messages: list[ChatMessage]) -> dict[str, Any]:
    return {"hold_id": last_tool_result(messages, "hold_id")["hold_id"]}


def next_open_day() -> str:
    day = datetime.now(TZ).date() + timedelta(days=2)
    return (day + timedelta(days=1) if day.weekday() == 6 else day).isoformat()


FORM = {
    "full_name": "Juan Dela Cruz",
    "date_of_birth": "1990-03-03",
    "phone": "09170000000",
    "reason": "Cough",
}


def say(ws: Any, text: str, turn_id: int) -> list[Event]:
    ws.send_json({"type": "text.message", "text": text, "ts": 1})
    return receive_until(ws, "agent.text.done", turn_id=turn_id)


def of_type(events: list[Event], type_: str) -> list[Event]:
    return [e for e in events if e["type"] == type_]


def tool_errors(llm: FakeLLM) -> list[str]:
    """Error codes the tools returned to the LLM so far in the call, in order."""
    codes = []
    for m in llm.calls[-1]:
        if m.role == "tool" and "error" in (data := json.loads(m.content)):
            codes.append(data["error"])
    return codes


# ---------- scenarios ----------


def test_book_a_new_appointment(sql_client: TestClient, llm: FakeLLM) -> None:
    day = next_open_day()
    llm.replies = [
        ToolStep(
            [
                ("update_intake_form", FORM),
                ("check_availability", {"date_from": day, "part_of_day": "any"}),
            ],
            text="Sure.",
        ),
        "I have a few times. Does the first one work?",
        ToolStep([("hold_slot", first_slot)]),
        "So that's the first slot. Shall I book it?",
        ToolStep([("confirm_booking", held)]),
        "You're booked. Please arrive 10 minutes early.",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        call_id = start_call(ws)[0]["call_id"]
        first = say(ws, "I'm Juan Dela Cruz, born March 3 1990, 0917, for a cough.", 1)
        second = say(ws, "The first one please", 2)
        third = say(ws, "Yes", 3)

    fields = {e["field"]: e["value"] for e in of_type(first, "form.field_updated")}
    assert fields == FORM
    offered = of_type(first, "calendar.slots_offered")[0]
    assert offered["date"] == day and offered["slots"]
    assert [e["name"] for e in of_type(first, "tool.finished")] == [
        "update_intake_form",
        "check_availability",
    ]
    assert text_of(first, 1).startswith("Sure. I have a few times.")

    holding = of_type(second, "calendar.slot_holding")[0]
    assert holding["start"] == offered["slots"][0]["start"]

    confirmed = of_type(third, "calendar.slot_confirmed")[0]
    assert confirmed["patient_name"] == "Juan Dela Cruz"
    assert confirmed["start"] == holding["start"]
    assert all(e["ok"] for e in of_type(first + second + third, "tool.finished"))

    async def check_db() -> tuple[str, list[str]]:
        """This call's booking and tool audit rows. Audits are written by a background queue
        just after each turn, so poll briefly instead of reading once."""
        sessionmaker = fresh_sessionmaker()
        names: list[str] = []
        for _ in range(50):
            async with sessionmaker() as db:
                row = await db.get(SandboxAppointment, uuid.UUID(confirmed["appointment_id"]))
                names = list(
                    await db.scalars(
                        select(ToolCall.name)
                        .join(Turn, Turn.id == ToolCall.turn_id)
                        .where(Turn.call_id == uuid.UUID(call_id))
                        .order_by(Turn.index)
                    )
                )
            if len(names) >= 4:
                break
            await asyncio.sleep(0.1)
        assert row is not None
        return row.status, names

    status, audited = asyncio.run(check_db())
    assert status == "confirmed"
    assert audited == ["update_intake_form", "check_availability", "hold_slot", "confirm_booking"]


def test_no_booking_without_readback_and_a_clear_yes(sql_client: TestClient, llm: FakeLLM) -> None:
    day = next_open_day()
    llm.replies = [
        ToolStep([("update_intake_form", FORM), ("check_availability", {"date_from": day})]),
        "Here are some times.",
        # Holding and then confirming within the same caller turn skips the read-back: refused.
        ToolStep([("hold_slot", first_slot)]),
        ToolStep([("confirm_booking", held)]),
        "Shall I book it?",
        # A question back is not a yes: refused.
        ToolStep([("confirm_booking", held)]),
        "Let me know when you're ready.",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        say(ws, "Book me in please", 1)
        second = say(ws, "The first one, go ahead and book it", 2)
        assert tool_errors(llm) == ["NEEDS_READBACK"]
        third = say(ws, "Wait, what time was that?", 3)
        assert tool_errors(llm) == ["NEEDS_READBACK", "NEEDS_CONFIRMATION"]

    assert of_type(second, "calendar.slot_holding")
    assert not of_type(second + third, "calendar.slot_confirmed")
    finished = of_type(third, "tool.finished")
    assert finished[0]["name"] == "confirm_booking" and finished[0]["ok"] is False


def test_booking_needs_the_required_form_fields(sql_client: TestClient, llm: FakeLLM) -> None:
    day = next_open_day()
    llm.replies = [
        ToolStep([("check_availability", {"date_from": day})]),
        "I have some times.",
        ToolStep([("hold_slot", first_slot)]),
        "Shall I book it?",
        ToolStep([("confirm_booking", held)]),
        "I just need a few details first.",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        say(ws, "Any time Tuesday", 1)
        say(ws, "The first one", 2)
        third = say(ws, "Yes please", 3)
    assert tool_errors(llm) == ["FORM_INCOMPLETE"]
    assert not of_type(third, "calendar.slot_confirmed")


def test_invalid_tool_arguments_get_a_clear_error(sql_client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [
        ToolStep([("check_availability", {"date_from": "next tuesday"})]),
        "Which date did you mean?",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        events = say(ws, "Next Tuesday", 1)
    assert of_type(events, "tool.finished")[0]["ok"] is False
    assert tool_errors(llm) == ["INVALID_ARGUMENTS"]


def test_transfer_to_staff(sql_client: TestClient, llm: FakeLLM) -> None:
    llm.replies = [
        ToolStep(
            [
                (
                    "end_call",
                    {"outcome": "transferred", "summary": "Billing dispute.", "transfer": True},
                )
            ]
        ),
        "Of course. Transferring you to the front desk now.",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "text.message", "text": "I want to talk to a person", "ts": 1})
        events = receive_until(ws, "call.ended")
    types = [e["type"] for e in events]
    assert (
        types.index("call.transferring")
        < types.index("agent.text.done")
        < types.index("call.ended")
    )
    assert events[-1]["outcome"] == "transferred"


def test_runaway_tool_loop_gives_up_politely(sql_client: TestClient, llm: FakeLLM) -> None:
    looping = ToolStep([("get_clinic_info", {"topic": "hours", "question": "hours?"})])
    llm.replies = [looping] * 4
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        events = say(ws, "What are your hours?", 1)
    assert len(of_type(events, "tool.finished")) == 4
    assert text_of(events, 1) == GIVE_UP_LINE


def test_at_most_three_tools_per_round(sql_client: TestClient, llm: FakeLLM) -> None:
    info = ("get_clinic_info", {"topic": "hours", "question": "hours?"})
    llm.replies = [ToolStep([info, info, info, info]), "We're open nine to five."]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        events = say(ws, "Hours?", 1)
    assert len(of_type(events, "tool.finished")) == 3
    assert tool_errors(llm) == ["TOO_MANY_TOOLS"]


def test_calendar_and_clinic_endpoints_show_only_this_sessions_bookings(
    sql_client: TestClient, llm: FakeLLM
) -> None:
    day = next_open_day()
    llm.replies = [
        ToolStep([("update_intake_form", FORM), ("check_availability", {"date_from": day})]),
        "I have some times.",
        ToolStep([("hold_slot", first_slot)]),
        "Shall I book it?",
        ToolStep([("confirm_booking", held)]),
        "Booked.",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        say(ws, "Book me in", 1)
        say(ws, "The first one", 2)
        booked = of_type(say(ws, "Yes", 3), "calendar.slot_confirmed")[0]

    auth = {"Authorization": f"Bearer {token}"}
    clinic = sql_client.get("/api/clinic", headers=auth).json()
    assert {d["id"] for d in clinic["doctors"]} == {"dr-reyes", "dr-cruz", "dr-santos"}

    mine = sql_client.get(f"/api/calendar?date={day}", headers=auth).json()
    assert [(a["id"], a["state"]) for a in mine["appointments"]] == [
        (booked["appointment_id"], "confirmed")
    ]
    assert all(b["id"].startswith("seed-") for b in mine["busy"])

    stranger = {"Authorization": f"Bearer {new_token(sql_client)}"}
    theirs = sql_client.get(f"/api/calendar?date={day}", headers=stranger).json()
    assert theirs["appointments"] == []
    sql_client.cookies.clear()  # the session cookie would otherwise authenticate the request
    assert sql_client.get(f"/api/calendar?date={day}").status_code == 401
    assert sql_client.get("/api/calendar?date=soon", headers=auth).status_code == 422


def test_end_call_waits_for_the_caller_to_be_done(sql_client: TestClient, llm: FakeLLM) -> None:
    end = ("end_call", {"outcome": "info_only", "summary": "Asked about hours."})
    llm.replies = [
        ToolStep([end]),
        "Is there anything else I can help with?",
        # Goodbye said in the same round as end_call: no second LLM round.
        ToolStep([end], text="Goodbye!"),
        "This must never be spoken.",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        first = say(ws, "What are your hours? Okay, thank you", 1)
        assert tool_errors(llm) == ["CALLER_NOT_DONE"]
        assert not of_type(first, "call.ended")
        ws.send_json({"type": "text.message", "text": "No, that's all. Bye!", "ts": 2})
        events = receive_until(ws, "call.ended")
    assert events[-1]["outcome"] == "info_only"
    assert text_of(events, 2) == "Goodbye!"


def test_goodbye_still_happens_if_the_llm_fails_after_end_call(
    sql_client: TestClient, llm: FakeLLM
) -> None:
    end = ("end_call", {"outcome": "info_only", "summary": "Said goodbye."})

    class FailAfterEnd(FakeLLM):
        async def stream(
            self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None = None
        ) -> AsyncIterator[LLMChunk]:
            if any(m.role == "tool" and "ending" in m.content for m in messages):
                raise ProviderError(ErrorCode.RATE_LIMITED, "busy")
            async for chunk in super().stream(messages, tools):
                yield chunk

    failing = FailAfterEnd(replies=[ToolStep([end])])
    sql_client.app.state.providers = Providers(stt=FakeSTT(), llm=failing)  # type: ignore[attr-defined]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "text.message", "text": "That's all, bye!", "ts": 1})
        events = receive_until(ws, "call.ended")
    assert text_of(events, 1) == GOODBYE_LINE
    assert events[-1]["outcome"] == "info_only"


def test_no_second_llm_round_after_mia_has_asked_her_question(
    sql_client: TestClient, llm: FakeLLM
) -> None:
    llm.replies = [
        ToolStep(
            [("update_intake_form", {"full_name": "Ana Cruz"})],
            text="Thanks. What's your birthday?",
        ),
        "This would be dropped anyway.",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        events = say(ws, "My name is Ana Cruz", 1)
    assert text_of(events, 1) == "Thanks. What's your birthday?"
    assert of_type(events, "form.field_updated")[0]["value"] == "Ana Cruz"
    assert len(llm.calls) == 1  # the tool ran, but no follow-up LLM call


def test_looking_up_the_patient_again_keeps_the_earlier_read_back(
    sql_client: TestClient, llm: FakeLLM
) -> None:
    async def a_seeded_appointment() -> tuple[str, str]:
        async with fresh_sessionmaker()() as db:
            row = (
                await db.execute(
                    select(SeedPatient.full_name, SeedPatient.date_of_birth)
                    .join(SeedAppointment, SeedAppointment.patient_id == SeedPatient.id)
                    .where(
                        SeedAppointment.start > datetime.now(TZ) + timedelta(days=1),
                        SeedAppointment.doctor_id != "dr-cruz",
                    )
                    .limit(1)
                )
            ).one()
        return row[0], row[1].isoformat()

    name, birthday = asyncio.run(a_seeded_appointment())
    patient = {"full_name": name, "date_of_birth": birthday}
    llm.replies = [
        ToolStep([("find_patient", patient)]),
        "I found your appointment. Shall I cancel it?",
        # In the "yes" turn the model looks the patient up again before cancelling.
        ToolStep([("find_patient", patient)]),
        ToolStep(
            [
                (
                    "cancel_appointment",
                    lambda m: {
                        "appointment_id": last_tool_result(m, "upcoming_appointments")[
                            "upcoming_appointments"
                        ][0]["appointment_id"]
                    },
                )
            ]
        ),
        "It's cancelled.",
    ]
    token = new_token(sql_client)
    with sql_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        say(ws, "I want to cancel my appointment", 1)
        events = say(ws, "Yes, cancel it", 2)
    assert of_type(events, "calendar.slot_cancelled")
