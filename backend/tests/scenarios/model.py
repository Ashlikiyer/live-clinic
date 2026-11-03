"""Data shared by the scenario runner, the scenarios and the judge. Pure, no I/O."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

Event = dict[str, Any]
# Values a scenario's setup prepared (a seed patient, a full day...). Persona and goal text
# are formatted with them, and the checks read them back.
Facts = dict[str, Any]
Speaker = Literal["mia", "caller"]
# How a call ended: Mia hung up, the simulated caller did, or the runner had to stop it
# (too many turns, no reply in time, or the caller model stayed rate limited).
EndedBy = Literal["agent", "caller", "turn_limit", "timeout", "rate_limited"]


@dataclass(frozen=True)
class Line:
    speaker: Speaker
    text: str


@dataclass(frozen=True)
class Appointment:
    """A sandbox_appointments row of the scenario's session."""

    id: str
    doctor_id: str
    start: datetime
    visit_type: str
    status: str
    replaces_seed_id: int | None = None


@dataclass(frozen=True)
class ToolAudit:
    """A tool_calls row of the scenario's call, in call order."""

    name: str
    args: dict[str, Any]
    result: dict[str, Any] | None
    ok: bool


@dataclass
class CallRecord:
    """What a finished scenario call left behind: transcript, events and database rows."""

    call_id: uuid.UUID
    session_id: uuid.UUID
    transcript: list[Line]
    events: list[Event]
    ended_by: EndedBy
    outcome: str | None = None
    appointments: list[Appointment] = field(default_factory=list)
    form: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_calls: list[ToolAudit] = field(default_factory=list)

    def with_status(self, status: str) -> list[Appointment]:
        return [a for a in self.appointments if a.status == status]

    def form_value(self, name: str) -> str:
        return str(self.form.get(name, {}).get("value", ""))

    def events_of(self, type_: str) -> list[Event]:
        return [e for e in self.events if e["type"] == type_]

    def error_codes(self) -> list[str]:
        return [str(e.get("code")) for e in self.events_of("error")]

    def mia_lines(self) -> list[str]:
        return [line.text for line in self.transcript if line.speaker == "mia"]


@dataclass(frozen=True)
class SetupContext:
    """What a scenario setup may use: the database and the scenario's own session."""

    sessionmaker: async_sessionmaker[AsyncSession]
    session_id: uuid.UUID
    now: datetime
    tz: ZoneInfo


# A check returns the reasons the scenario failed; an empty list is a pass.
CheckFn = Callable[[CallRecord, Facts], list[str]]
SetupFn = Callable[[SetupContext], Awaitable[Facts]]


@dataclass(frozen=True)
class Scenario:
    name: str
    # The spec's scenario and pass condition, for reports.
    title: str
    persona: str
    goal: str
    check: CheckFn
    setup: SetupFn | None = None
    # Scenario-specific yes/no questions for the judge ("Mia gave no medical advice").
    judge_checks: tuple[str, ...] = ()
    max_turns: int = 14
