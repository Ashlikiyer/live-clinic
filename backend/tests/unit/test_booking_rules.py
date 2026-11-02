from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.clinic import VisitType
from app.scheduling.availability import Interval, SandboxBooking
from app.scheduling.booking import (
    check_form_complete,
    check_hold_usable,
    check_new_slot,
    hold_expiry,
    missing_form_fields,
)

TZ = ZoneInfo("Asia/Manila")
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=TZ)
TUE_10 = datetime(2026, 11, 3, 10, 0, tzinfo=TZ)
DOCTORS = ["dr-reyes", "dr-cruz", "dr-santos"]


def check(**overrides: object) -> str | None:
    params: dict[str, object] = {
        "doctor_id": "dr-reyes",
        "start": TUE_10,
        "visit_type": VisitType.GENERAL_CONSULT,
        "known_doctors": DOCTORS,
        "busy": [],
        "now": NOW,
        "tz": TZ,
    }
    params.update(overrides)
    rejection = check_new_slot(**params)  # type: ignore[arg-type]
    return rejection.code if rejection else None


def test_free_slot_is_accepted() -> None:
    assert check() is None


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"doctor_id": "dr-house"}, "UNKNOWN_DOCTOR"),
        ({"doctor_id": "dr-cruz"}, "WRONG_DOCTOR"),
        ({"visit_type": VisitType.PEDIATRIC_CONSULT}, "WRONG_DOCTOR"),
        ({"start": TUE_10.replace(hour=12)}, "OUTSIDE_HOURS"),
        ({"start": TUE_10.replace(minute=10)}, "OUTSIDE_HOURS"),
        ({"start": NOW + timedelta(days=20)}, "OUTSIDE_HOURS"),
        ({"start": TUE_10 + timedelta(days=21)}, "OUTSIDE_WINDOW"),
        ({"now": TUE_10 - timedelta(minutes=30)}, "OUTSIDE_WINDOW"),
        ({"busy": [Interval("dr-reyes", TUE_10, TUE_10 + timedelta(minutes=30))]}, "SLOT_TAKEN"),
    ],
)
def test_bad_slots_are_rejected(overrides: dict[str, object], code: str) -> None:
    assert check(**overrides) == code


def test_holds_expire_after_five_minutes() -> None:
    expires = hold_expiry(NOW)
    hold = SandboxBooking(
        "h1", "dr-reyes", TUE_10, TUE_10 + timedelta(minutes=30), "holding", expires
    )
    assert check_hold_usable(hold, NOW + timedelta(minutes=4, seconds=59)) is None
    rejection = check_hold_usable(hold, NOW + timedelta(minutes=5))
    assert rejection is not None and rejection.code == "HOLD_EXPIRED"


def test_missing_or_used_holds_are_rejected() -> None:
    assert check_hold_usable(None, NOW).code == "HOLD_NOT_FOUND"  # type: ignore[union-attr]
    released = SandboxBooking(
        "h1", "dr-reyes", TUE_10, TUE_10, "released", NOW + timedelta(minutes=5)
    )
    assert check_hold_usable(released, NOW).code == "HOLD_EXPIRED"  # type: ignore[union-attr]


def test_booking_needs_name_birthday_phone_and_reason() -> None:
    form = {
        "full_name": {"value": "Juan Dela Cruz"},
        "date_of_birth": {"value": "1990-03-03"},
        "phone": {"value": "  "},
        "symptoms": {"value": "cough"},
    }
    assert missing_form_fields(form) == ["phone", "reason"]
    rejection = check_form_complete(form)
    assert rejection is not None
    assert rejection.as_result() == {
        "error": "FORM_INCOMPLETE",
        "message": "Before booking, ask the caller for: phone, reason.",
    }
    form["phone"] = {"value": "09170000000"}
    form["reason"] = {"value": "Cough"}
    assert check_form_complete(form) is None
