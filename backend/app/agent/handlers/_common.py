"""Small helpers shared by the tool handlers."""

from typing import Any
from zoneinfo import ZoneInfo

from app.agent.spoken import clinic_iso, spoken_time
from app.repositories.booking import Booking, DoctorInfo


def doctor_name(doctors: list[DoctorInfo], doctor_id: str) -> str:
    return next((d.name for d in doctors if d.id == doctor_id), doctor_id)


def describe(booking: Booking, doctors: list[DoctorInfo], tz: ZoneInfo) -> dict[str, Any]:
    """What the LLM needs to read an appointment back (ids are for tool calls, never spoken)."""
    return {
        "doctor": doctor_name(doctors, booking.doctor_id),
        "doctor_id": booking.doctor_id,
        "when": spoken_time(booking.start, tz),
        "visit_type": booking.visit_type,
        "start": clinic_iso(booking.start, tz),
    }
