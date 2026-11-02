"""Seeded, read-only clinic data shared by every session."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clinic import ClinicTopic, VisitType
from app.db.base import Base, in_values


class Doctor(Base):
    __tablename__ = "doctors"

    # Short readable slug (e.g. "dr-reyes") so tool arguments stay LLM-friendly.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    specialty: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(7))
    active: Mapped[bool] = mapped_column(default=True)


class ClinicInfo(Base):
    __tablename__ = "clinic_info"
    __table_args__ = (CheckConstraint(in_values("topic", ClinicTopic), name="topic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(20), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)


class SeedPatient(Base):
    __tablename__ = "seed_patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    date_of_birth: Mapped[date] = mapped_column(Date)
    phone: Mapped[str] = mapped_column(String(20))


class SeedAppointment(Base):
    __tablename__ = "seed_appointments"
    __table_args__ = (
        CheckConstraint(in_values("visit_type", VisitType), name="visit_type"),
        CheckConstraint('start < "end"', name="start_before_end"),
        Index("ix_seed_appointments_doctor_start", "doctor_id", "start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("seed_patients.id"))
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    visit_type: Mapped[str] = mapped_column(String(32))
