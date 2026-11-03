"""Per-visitor data. Everything here hangs off `sessions` and is deleted after 24 hours."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clinic import AppointmentStatus, CallOutcome, TurnRole, VisitType
from app.db.base import Base, in_values


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class SandboxSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_ip_hash_created_at", "ip_hash", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    ip_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        CheckConstraint(f"outcome IS NULL OR {in_values('outcome', CallOutcome)}", name="outcome"),
        CheckConstraint("voice_mode IN ('kokoro', 'lite')", name="voice_mode"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = _created_at()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(Text)
    voice_mode: Mapped[str] = mapped_column(String(10), default="kokoro")
    turn_count: Mapped[int] = mapped_column(default=0)


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (
        CheckConstraint(in_values("role", TurnRole), name="role"),
        UniqueConstraint("call_id", "index", name="uq_turns_call_id_index"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text, default="")
    interrupted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = _created_at()


class TurnMetrics(Base):
    __tablename__ = "turn_metrics"

    turn_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), primary_key=True
    )
    vad_wait_ms: Mapped[int | None]
    upload_ms: Mapped[int | None]
    stt_ms: Mapped[int | None]
    llm_ttft_ms: Mapped[int | None]
    first_sentence_ms: Mapped[int | None]
    tts_ms: Mapped[int | None]
    total_ms: Mapped[int | None]
    # Barge-in only: caller started speaking -> agent audio stopped, measured in the browser.
    stop_ms: Mapped[int | None]


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = _uuid_pk()
    turn_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(40))
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ok: Mapped[bool] = mapped_column(default=False)
    ms: Mapped[int | None]


class SandboxAppointment(Base):
    __tablename__ = "sandbox_appointments"
    __table_args__ = (
        CheckConstraint(in_values("status", AppointmentStatus), name="status"),
        CheckConstraint(in_values("visit_type", VisitType), name="visit_type"),
        CheckConstraint('start < "end"', name="start_before_end"),
        Index("ix_sandbox_appointments_session_start", "session_id", "start"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"))
    # "seed:<id>" for a seeded patient, or "call:<call_id>" for a caller-provided one.
    patient_ref: Mapped[str | None] = mapped_column(String(64))
    patient_name: Mapped[str | None] = mapped_column(String(100))
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    visit_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(12))
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when this row cancels or moves a seeded appointment, freeing its slot for this session.
    replaces_seed_id: Mapped[int | None] = mapped_column(
        ForeignKey("seed_appointments.id", ondelete="SET NULL")
    )


class IntakeForm(Base):
    __tablename__ = "intake_forms"

    id: Mapped[uuid.UUID] = _uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), unique=True
    )
    # {field: {"value": str, "corrected": bool}}
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
