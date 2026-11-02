"""The agent's ten tools: Pydantic argument models and the JSON schemas sent to the LLM."""

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=200)]
VisitTypeName = Literal["general_consult", "follow_up", "pediatric_consult", "annual_checkup"]
OutcomeName = Literal[
    "booked",
    "rescheduled",
    "cancelled",
    "info_only",
    "transferred",
    "emergency_advised",
    "abandoned",
]
MAX_SEARCH_DAYS = 14


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UpdateIntakeFormArgs(_Args):
    full_name: Text | None = None
    date_of_birth: date | None = None
    phone: Text | None = None
    reason: Text | None = None
    symptoms: Text | None = None
    symptom_duration: Text | None = None
    allergies: Text | None = None
    insurance: Text | None = None
    preferred_doctor: Text | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> "UpdateIntakeFormArgs":
        if not self.model_dump(exclude_none=True):
            raise ValueError("Give at least one field.")
        return self


class FindPatientArgs(_Args):
    full_name: Text
    date_of_birth: date


class CheckAvailabilityArgs(_Args):
    date_from: date
    date_to: date | None = None
    part_of_day: Literal["morning", "afternoon", "any"] = "any"
    doctor_id: str | None = None
    visit_type: VisitTypeName = "general_consult"

    @model_validator(mode="after")
    def _range(self) -> "CheckAvailabilityArgs":
        last = self.date_to or self.date_from
        if last < self.date_from:
            raise ValueError("date_to must not be before date_from.")
        if (last - self.date_from).days > MAX_SEARCH_DAYS:
            raise ValueError("Search at most 14 days at a time.")
        return self


class HoldSlotArgs(_Args):
    slot_start: datetime
    doctor_id: str
    visit_type: VisitTypeName = "general_consult"


class HoldIdArgs(_Args):
    hold_id: str


class RescheduleAppointmentArgs(_Args):
    appointment_id: str
    new_hold_id: str


class CancelAppointmentArgs(_Args):
    appointment_id: str


class GetClinicInfoArgs(_Args):
    topic: Literal["hours", "location", "services", "doctors", "prices", "preparation", "other"]
    question: Annotated[str, Field(min_length=1, max_length=300)]


class EndCallArgs(_Args):
    outcome: OutcomeName
    summary: Annotated[str, Field(min_length=1, max_length=500)]
    transfer: bool = False


ARG_MODELS: dict[str, type[_Args]] = {
    "update_intake_form": UpdateIntakeFormArgs,
    "find_patient": FindPatientArgs,
    "check_availability": CheckAvailabilityArgs,
    "hold_slot": HoldSlotArgs,
    "confirm_booking": HoldIdArgs,
    "release_hold": HoldIdArgs,
    "reschedule_appointment": RescheduleAppointmentArgs,
    "cancel_appointment": CancelAppointmentArgs,
    "get_clinic_info": GetClinicInfoArgs,
    "end_call": EndCallArgs,
}

# Kept short on purpose: every word is sent on every LLM call, and the free tier counts tokens.
DESCRIPTIONS = {
    "update_intake_form": "Save form details as soon as the caller gives them, or corrects one.",
    "find_patient": "Find an existing patient and their upcoming appointments.",
    "check_availability": "Find free slots. Offer only these.",
    "hold_slot": "Hold a slot for 5 minutes, then read it back.",
    "confirm_booking": "Book the held slot after the caller's yes.",
    "release_hold": "Release an unwanted hold.",
    "reschedule_appointment": "Move an appointment to a held slot after the caller's yes.",
    "cancel_appointment": "Cancel an appointment after the caller's yes.",
    "get_clinic_info": "Clinic facts. Never answer these from memory.",
    "end_call": "End the call after goodbye. transfer=true hands over to staff.",
}

# Validation details the server enforces anyway; leaving them out saves tokens on every call.
_DROP_KEYS = {"title", "default", "minLength", "maxLength", "additionalProperties"}


def _clean(schema: Any) -> Any:
    """Simplify Pydantic's schema for the LLM: no titles, `X | None` becomes plain `X`."""
    if isinstance(schema, dict):
        if "anyOf" in schema:
            options = [o for o in schema["anyOf"] if o.get("type") != "null"]
            if len(options) == 1:
                merged = {**schema, **options[0]}
                merged.pop("anyOf")
                schema = merged
        return {k: _clean(v) for k, v in schema.items() if k not in _DROP_KEYS}
    if isinstance(schema, list):
        return [_clean(v) for v in schema]
    return schema


def tool_specs() -> list[dict[str, Any]]:
    """OpenAI-style tool definitions for the LLM."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": _clean(model.model_json_schema()),
            },
        }
        for name, model in ARG_MODELS.items()
    ]
