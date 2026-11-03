"""The scenario runner end to end with fake providers: Mia, the caller and the judge are all
scripted, so this runs in CI without Groq. Skipped when Postgres isn't reachable."""

import asyncio
import dataclasses
import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from anyio.from_thread import BlockingPortal, start_blocking_portal
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.call.session import ToolDeps
from app.core.config import get_settings
from app.db.models import Doctor
from app.db.session import check_database, get_engine, get_sessionmaker
from app.main import create_app
from app.providers.base import ChatMessage, Providers
from app.providers.fake import FakeLLM, FakeSTT, ToolStep
from app.repositories.booking import BookingRepository
from app.repositories.calls import SqlCallStore
from app.repositories.clinic import ClinicInfoRepository
from seed.__main__ import seed
from tests.scenarios.caller import HANGUP
from tests.scenarios.runner import ScenarioRunner, scenario_settings
from tests.scenarios.scenarios import BY_NAME, open_day_after

TZ = ZoneInfo("Asia/Manila")
JUDGE_REPLY = json.dumps({"politeness": 5, "brevity": 4, "one_question": 5, "notes": "none"})


async def _prepare_database() -> bool:
    if not await check_database():
        return False
    async with get_sessionmaker()() as db:
        if not await db.scalar(select(func.count()).select_from(Doctor)):
            await seed(db)
    await get_engine().dispose()
    return True


class Rig:
    """The app with a scripted Mia, plus a runner with a scripted caller and judge."""

    def __init__(self, client: TestClient, portal: BlockingPortal, sm: Any) -> None:
        self.client, self.portal, self.sessionmaker = client, portal, sm

    def runner(self, caller: FakeLLM, judge: FakeLLM | None = None) -> ScenarioRunner:
        return ScenarioRunner(
            self.client,
            self.portal,
            self.sessionmaker,
            get_settings(),
            caller,
            judge,
            backoff_s=0,
            log=lambda _: None,
        )


@pytest.fixture
def mia() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def rig(mia: FakeLLM) -> Iterator[Rig]:
    if not asyncio.run(_prepare_database()):
        pytest.skip("Postgres not reachable at DATABASE_URL")
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    sm: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(
        store=SqlCallStore(sm),
        providers=Providers(stt=FakeSTT(), llm=mia),
        tools=ToolDeps(BookingRepository(sm, TZ), ClinicInfoRepository(sm)),
    )
    with (
        scenario_settings(get_settings(), None),
        start_blocking_portal() as portal,
        TestClient(app) as client,
    ):
        yield Rig(client, portal, sm)


def _last_result(messages: list[ChatMessage], key: str) -> dict[str, Any]:
    for m in reversed(messages):
        if m.role == "tool" and key in (data := json.loads(m.content)):
            return data  # type: ignore[no-any-return]
    raise AssertionError(f"no tool result with {key!r}")


def _first_slot(messages: list[ChatMessage]) -> dict[str, Any]:
    slot = _last_result(messages, "slots")["slots"][0]
    return {"slot_start": slot["slot_start"], "doctor_id": slot["doctor_id"]}


def test_a_booking_scenario_passes_its_database_checks_and_is_judged(
    rig: Rig, mia: FakeLLM
) -> None:
    day = open_day_after(datetime.now(TZ).date(), 2).isoformat()
    form = {
        "full_name": "Juan Dela Cruz",
        "date_of_birth": "1990-03-03",
        "phone": "09175550142",
        "reason": "Cough",
    }
    mia.replies = [
        ToolStep(
            [("update_intake_form", form), ("check_availability", {"date_from": day})],
            text="Sure.",
        ),
        "I have a time open. Does it work?",
        ToolStep([("hold_slot", _first_slot)]),
        "That's with the doctor. Shall I book it?",
        ToolStep(
            [("confirm_booking", lambda m: {"hold_id": _last_result(m, "hold_id")["hold_id"]})]
        ),
        "You're booked. Anything else?",
        ToolStep(
            [("end_call", {"outcome": "booked", "summary": "Booked a consult for a cough."})],
            text="Thanks for calling. Goodbye!",
        ),
    ]
    caller = FakeLLM(
        replies=[
            "I'm Juan Dela Cruz, born March 3 1990, phone 0917 555 0142, for a cough.",
            "Yes, the first one.",
            "Yes please.",
            "That's all, thanks. Bye!",
            HANGUP,
        ]
    )
    judge = FakeLLM(replies=[JUDGE_REPLY])

    result = rig.runner(caller, judge).run(BY_NAME["new_patient_cough"])

    assert result.failures == [] and result.passed
    assert result.record.ended_by == "agent"
    assert result.record.outcome == "booked"
    assert [line.speaker for line in result.record.transcript] == ["mia", "caller"] * 4 + ["mia"]
    assert result.record.transcript[-1].text == "Thanks for calling. Goodbye!"
    assert [t.name for t in result.record.tool_calls] == [
        "update_intake_form",
        "check_availability",
        "hold_slot",
        "confirm_booking",
        "end_call",
    ]
    assert result.judgement is not None
    assert result.judgement.scores == {"politeness": 5, "brevity": 4, "one_question": 5}
    # The judge saw the whole call.
    judged = judge.calls[0][-1].content
    assert "Caller: Yes please." in judged and "Mia: You're booked." in judged


def test_a_failed_check_is_reported_and_the_caller_can_hang_up(rig: Rig, mia: FakeLLM) -> None:
    mia.replies = ["Sure. What day would you like?"]
    caller = FakeLLM(replies=[f"Never mind, bye. {HANGUP}"])

    result = rig.runner(caller).run(BY_NAME["new_patient_cough"])

    assert result.record.ended_by == "caller"
    assert not result.passed
    assert "0 confirmed appointments, expected 1" in result.failures
    assert result.record.outcome == "info_only"
    assert result.judgement is None


def test_chest_pain_ends_the_call_before_the_llm(rig: Rig, mia: FakeLLM) -> None:
    caller = FakeLLM(replies=["I'd like a check-up. I've had chest pain for an hour."])

    result = rig.runner(caller).run(BY_NAME["chest_pain"])

    assert result.passed, result.failures
    assert result.record.ended_by == "agent"
    assert mia.calls == []  # the emergency check answered, not the LLM


def test_the_full_day_setup_blocks_the_day_and_finds_the_nearest_free_one(
    rig: Rig, mia: FakeLLM
) -> None:
    def check(day_key: str) -> Any:
        return lambda _m: {"date_from": facts_holder[day_key]}

    facts_holder: dict[str, str] = {}
    scenario = BY_NAME["requested_day_full"]
    assert scenario.setup is not None
    setup = scenario.setup

    async def capture(ctx: Any) -> Any:
        facts = await setup(ctx)
        facts_holder["full"] = facts["full_day_start"].date().isoformat()
        facts_holder["nearest"] = facts["nearest_day"]
        return facts

    mia.replies = [
        ToolStep([("check_availability", check("full"))]),
        ToolStep([("check_availability", check("nearest"))]),
        "That day is full, but the next day is open. Would that work?",
    ]
    caller = FakeLLM(replies=["Any time on that day please.", f"Bye. {HANGUP}"])
    patched = dataclasses.replace(scenario, setup=capture)

    result = rig.runner(caller).run(patched)

    first, second = (t.result or {} for t in result.record.tool_calls[:2])
    assert first["slots"] == []  # every doctor's day is filled
    assert second["slots"]
    assert result.failures == []
