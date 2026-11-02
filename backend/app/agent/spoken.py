"""How times and dates are said aloud. Pure, no I/O."""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def spoken_date(day: date) -> str:
    """'Tuesday, November 3'."""
    return f"{day:%A}, {day:%B} {day.day}"


def spoken_time(moment: datetime, tz: ZoneInfo) -> str:
    """'Tuesday, November 3, at 2:30 PM' (clinic time)."""
    local = moment.astimezone(tz)
    clock = f"{local.hour % 12 or 12}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"
    return f"{spoken_date(local.date())}, at {clock}"


def clinic_iso(moment: datetime, tz: ZoneInfo) -> str:
    """Clinic-time ISO 8601 with offset, as calendar events expect: 2026-11-03T14:30:00+08:00."""
    return moment.astimezone(tz).isoformat(timespec="seconds")
