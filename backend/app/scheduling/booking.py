"""Booking rules. Pure functions, no I/O: they decide, the repository applies.

Every rejection carries a short code and a message the LLM can act on, e.g.
{"error": "SLOT_TAKEN", "message": "That time was just taken. Offer another slot."}.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.clinic import HOLD_MINUTES, VisitType
from app.scheduling.availability import (
    Interval,
    SandboxBooking,
    doctor_allowed,
    fits_clinic_hours,
    in_booking_window,
    is_free,
    visit_minutes,
)

REQUIRED_FORM_FIELDS = ("full_name", "date_of_birth", "phone", "reason")


@dataclass(frozen=True)
class Rejection:
    code: str
    message: str

    def as_result(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message}


def check_new_slot(
    *,
    doctor_id: str,
    start: datetime,
    visit_type: VisitType,
    known_doctors: Iterable[str],
    busy: Iterable[Interval],
    now: datetime,
    tz: ZoneInfo,
) -> Rejection | None:
    """Can this session hold `start` with `doctor_id`? None means yes."""
    if doctor_id not in set(known_doctors):
        return Rejection(
            "UNKNOWN_DOCTOR",
            "That doctor doesn't work here. Use a doctor_id from check_availability.",
        )
    if not doctor_allowed(doctor_id, visit_type):
        return Rejection(
            "WRONG_DOCTOR",
            "Children see Dr. Paolo Cruz (pediatric_consult); adults see Dr. Reyes or Dr. Santos.",
        )
    minutes = visit_minutes(visit_type)
    if not fits_clinic_hours(start, minutes, tz):
        return Rejection(
            "OUTSIDE_HOURS",
            "That time is outside clinic hours or over lunch. Use a time from check_availability.",
        )
    if not in_booking_window(start, now, tz):
        return Rejection(
            "OUTSIDE_WINDOW",
            "Bookings must be at least an hour from now and within the next 14 days.",
        )
    if not is_free(doctor_id, start, start + timedelta(minutes=minutes), busy):
        return Rejection("SLOT_TAKEN", "That time is no longer free. Check availability again.")
    return None


def hold_expiry(now: datetime) -> datetime:
    return now + timedelta(minutes=HOLD_MINUTES)


def check_hold_usable(hold: SandboxBooking | None, now: datetime) -> Rejection | None:
    """A hold must exist in this session and still be active."""
    if hold is None:
        return Rejection("HOLD_NOT_FOUND", "There is no such hold. Hold a slot first.")
    if not hold.is_active_hold(now):
        return Rejection(
            "HOLD_EXPIRED", "That hold has expired. Check availability and hold again."
        )
    return None


def missing_form_fields(form: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Required intake fields that are still empty. `form` is {field: {"value": ...}}."""
    return [f for f in REQUIRED_FORM_FIELDS if not str(form.get(f, {}).get("value", "")).strip()]


def check_form_complete(form: Mapping[str, Mapping[str, Any]]) -> Rejection | None:
    missing = missing_form_fields(form)
    if not missing:
        return None
    return Rejection(
        "FORM_INCOMPLETE",
        f"Before booking, ask the caller for: {', '.join(m.replace('_', ' ') for m in missing)}.",
    )
