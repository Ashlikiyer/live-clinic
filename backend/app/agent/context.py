"""What a tool handler can see and change. One ToolContext per tool call."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.providers.base import LLMProvider
from app.repositories.booking import BookingRepository
from app.repositories.clinic import ClinicInfoRepository
from app.scheduling.booking import Rejection


@dataclass(frozen=True)
class EndRequest:
    outcome: str
    summary: str
    transfer: bool


@dataclass
class CallToolState:
    """Per-call memory that tool rules depend on, kept across turns."""

    # hold_id / appointment_id -> the turn in which it was presented to the caller. A change is
    # only confirmed in a *later* turn, so the read-back always happens before the "yes".
    presented: dict[str, int] = field(default_factory=dict)
    # turn_id -> result of the LLM yes/no check, so it runs at most once per caller turn.
    confirm_checks: dict[int, bool] = field(default_factory=dict)
    # Existing appointments find_patient returned: the caller may want to move one.
    found_appointments: list[str] = field(default_factory=list)
    outcome: str | None = None
    # Booking changes that really succeeded in this call ("booked", "cancelled"...), so the
    # call can't be closed with an outcome that never happened.
    completed: set[str] = field(default_factory=set)
    end_request: EndRequest | None = None
    callback_notes: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """`data` goes back to the LLM as JSON; `events` go to the browser (type, payload)."""

    data: dict[str, Any]
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    ok: bool = True

    @classmethod
    def rejected(cls, rejection: Rejection) -> "ToolResult":
        return cls(rejection.as_result(), ok=False)


@dataclass
class ToolContext:
    session_id: uuid.UUID
    call_id: uuid.UUID
    turn_id: int
    last_user_text: str
    repo: BookingRepository
    clinic: ClinicInfoRepository
    llm: LLMProvider
    tz: ZoneInfo
    state: CallToolState

    def now(self) -> datetime:
        return datetime.now(self.tz)
