"""Clinic details and the calendar for the caller's sandbox."""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.agent.spoken import clinic_iso
from app.core.clinic import CLINIC_NAME
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.routers.deps import CurrentSession, Tools

router = APIRouter()


def _require_tools(tools: Tools) -> Any:
    if tools is None:
        raise AppError(ErrorCode.INTERNAL_ERROR, "Calendar is unavailable.", 503)
    return tools


@router.get("/api/clinic")
async def clinic(session: CurrentSession, tools: Tools) -> dict[str, Any]:
    tz = ZoneInfo(get_settings().clinic_timezone)
    doctors = await _require_tools(tools).booking.doctors()
    return {
        "name": CLINIC_NAME,
        "timezone": str(tz),
        "today": datetime.now(tz).date().isoformat(),
        "hours": "Monday to Saturday, 9:00 AM to 5:00 PM; lunch 12:00 to 1:00 PM",
        "doctors": [
            {"id": d.id, "name": d.name, "specialty": d.specialty, "color": d.color}
            for d in doctors
        ],
    }


@router.get("/api/calendar")
async def calendar(date: date, session: CurrentSession, tools: Tools) -> dict[str, Any]:
    """Seeded busy slots plus this session's own holds and bookings for one day."""
    tz = ZoneInfo(get_settings().clinic_timezone)
    repo = _require_tools(tools).booking
    busy, own = await repo.calendar_day(session.id, date, datetime.now(tz))
    return {
        "date": date.isoformat(),
        "busy": [
            {
                "id": public_id,
                "doctor_id": s.doctor_id,
                "start": clinic_iso(s.start, tz),
                "end": clinic_iso(s.end, tz),
            }
            for public_id, s in busy
        ],
        "appointments": [
            {
                "id": a.id,
                "doctor_id": a.doctor_id,
                "start": clinic_iso(a.start, tz),
                "end": clinic_iso(a.end, tz),
                "state": a.status,
                "patient_name": a.patient_name,
                "expires_at": clinic_iso(a.hold_expires_at, tz) if a.hold_expires_at else None,
            }
            for a in own
        ],
    }
