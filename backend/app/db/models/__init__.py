"""Importing this package registers every table on `Base.metadata`."""

from app.db.models.calls import (
    Call,
    IntakeForm,
    SandboxAppointment,
    SandboxSession,
    ToolCall,
    Turn,
    TurnMetrics,
)
from app.db.models.clinic import ClinicInfo, Doctor, SeedAppointment, SeedPatient
from app.db.models.stats import DailyStats

__all__ = [
    "Call",
    "ClinicInfo",
    "DailyStats",
    "Doctor",
    "IntakeForm",
    "SandboxAppointment",
    "SandboxSession",
    "SeedAppointment",
    "SeedPatient",
    "ToolCall",
    "Turn",
    "TurnMetrics",
]
