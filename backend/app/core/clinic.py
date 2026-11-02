"""Fixed clinic rules from the spec. Pure constants, shared by seeding and scheduling."""

from datetime import time
from enum import StrEnum

CLINIC_NAME = "Bayview Family Clinic"
OPEN_TIME = time(9, 0)
CLOSE_TIME = time(17, 0)
LUNCH_START = time(12, 0)
LUNCH_END = time(13, 0)
SLOT_MINUTES = 30
# Monday=0 ... Saturday=5 (datetime.weekday()).
OPEN_WEEKDAYS = frozenset(range(6))
BOOKING_WINDOW_DAYS = 14
MIN_LEAD_MINUTES = 60
HOLD_MINUTES = 5


class VisitType(StrEnum):
    GENERAL_CONSULT = "general_consult"
    FOLLOW_UP = "follow_up"
    PEDIATRIC_CONSULT = "pediatric_consult"
    ANNUAL_CHECKUP = "annual_checkup"


VISIT_MINUTES: dict[VisitType, int] = {
    VisitType.GENERAL_CONSULT: 30,
    VisitType.FOLLOW_UP: 30,
    VisitType.PEDIATRIC_CONSULT: 30,
    VisitType.ANNUAL_CHECKUP: 60,
}


class CallOutcome(StrEnum):
    BOOKED = "booked"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    INFO_ONLY = "info_only"
    TRANSFERRED = "transferred"
    EMERGENCY_ADVISED = "emergency_advised"
    ABANDONED = "abandoned"


class TurnRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AppointmentStatus(StrEnum):
    HOLDING = "holding"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    RELEASED = "released"


class ClinicTopic(StrEnum):
    HOURS = "hours"
    LOCATION = "location"
    SERVICES = "services"
    DOCTORS = "doctors"
    PRICES = "prices"
    PREPARATION = "preparation"
    OTHER = "other"
