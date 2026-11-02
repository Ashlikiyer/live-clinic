"""One handler per tool. `run_tool` validates arguments, runs the handler, and never raises."""

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agent.context import ToolContext, ToolResult
from app.agent.handlers import (
    cancel_appointment,
    check_availability,
    confirm_booking,
    end_call,
    find_patient,
    get_clinic_info,
    hold_slot,
    release_hold,
    reschedule_appointment,
    update_intake_form,
)
from app.agent.tools import ARG_MODELS
from app.providers.base import ToolCallRequest

log = logging.getLogger(__name__)

Handler = Callable[[ToolContext, Any], Awaitable[ToolResult]]

HANDLERS: dict[str, Handler] = {
    "update_intake_form": update_intake_form.handle,
    "find_patient": find_patient.handle,
    "check_availability": check_availability.handle,
    "hold_slot": hold_slot.handle,
    "confirm_booking": confirm_booking.handle,
    "release_hold": release_hold.handle,
    "reschedule_appointment": reschedule_appointment.handle,
    "cancel_appointment": cancel_appointment.handle,
    "get_clinic_info": get_clinic_info.handle,
    "end_call": end_call.handle,
}


@dataclass
class ToolRun:
    request: ToolCallRequest
    args: dict[str, Any]
    result: ToolResult
    ms: int

    def content(self) -> str:
        # Compact JSON: tool results stay in the LLM history, and tokens are rate limited.
        return json.dumps(self.result.data, default=str, separators=(",", ":"))


def _failure(code: str, message: str) -> ToolResult:
    return ToolResult({"error": code, "message": message}, ok=False)


def _validation_message(exc: ValidationError) -> str:
    problems = [
        f"{'.'.join(str(p) for p in err['loc']) or 'arguments'}: {err['msg']}"
        for err in exc.errors()[:3]
    ]
    return "Invalid arguments. " + "; ".join(problems)


async def run_tool(ctx: ToolContext, request: ToolCallRequest) -> ToolRun:
    started = time.perf_counter()
    args: dict[str, Any] = {}
    try:
        raw = json.loads(request.arguments or "{}")
        args = raw if isinstance(raw, dict) else {}
        handler = HANDLERS.get(request.name)
        model = ARG_MODELS.get(request.name)
        if handler is None or model is None:
            result = _failure("UNKNOWN_TOOL", "No such tool.")
        else:
            parsed: BaseModel = model.model_validate(raw)
            result = await handler(ctx, parsed)
    except json.JSONDecodeError:
        result = _failure("INVALID_ARGUMENTS", "Arguments must be a JSON object.")
    except ValidationError as exc:
        result = _failure("INVALID_ARGUMENTS", _validation_message(exc))
    except Exception:
        # A broken tool must not end the call; the LLM gets an error it can recover from.
        log.exception("Tool %s failed", request.name)
        result = _failure("TOOL_FAILED", "That didn't work. Apologize and offer a staff callback.")
    return ToolRun(request, args, result, round((time.perf_counter() - started) * 1000))
