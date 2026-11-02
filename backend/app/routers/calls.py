"""A finished call's summary, transcript, form and metrics. Own calls only (others are 404)."""

import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.clinic import CLINIC_NAME
from app.core.errors import AppError, ErrorCode
from app.repositories.calls import CallInfo, TurnRow
from app.routers.deps import CurrentSession, Store, Tools

router = APIRouter()

SPEAKER = {"user": "Caller", "assistant": "Mia", "tool": "System"}


async def _own_call(call_id: str, session: CurrentSession, store: Store) -> CallInfo:
    try:
        parsed = uuid.UUID(call_id)
    except ValueError:
        parsed = None
    call = await store.get_call(parsed, session.id) if parsed else None
    if call is None:
        raise AppError(ErrorCode.NOT_FOUND, "Call not found.", 404)
    return call


def transcript_lines(turns: list[TurnRow]) -> list[str]:
    return [
        f"{SPEAKER.get(t.role, t.role)}: {t.text}{' [interrupted]' if t.interrupted else ''}"
        for t in turns
        if t.text
    ]


@router.get("/api/calls/{call_id}")
async def call_detail(
    call_id: str, session: CurrentSession, store: Store, tools: Tools
) -> dict[str, Any]:
    call = await _own_call(call_id, session, store)
    turns = await store.list_turns(call.id)
    form = await tools.booking.form(call.id) if tools else {}
    return {
        "call_id": str(call.id),
        "started_at": call.started_at.isoformat(),
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "outcome": call.outcome,
        "summary": call.summary,
        "transcript": [
            {"role": t.role, "text": t.text, "interrupted": t.interrupted} for t in turns
        ],
        "form": form,
        "metrics": call.metrics,
    }


@router.get("/api/calls/{call_id}/transcript.txt", response_class=PlainTextResponse)
async def call_transcript(call_id: str, session: CurrentSession, store: Store) -> str:
    call = await _own_call(call_id, session, store)
    lines = [f"{CLINIC_NAME} (demo) - call transcript", f"Outcome: {call.outcome or 'in progress'}"]
    if call.summary:
        lines.append(call.summary)
    lines.append("")
    lines += transcript_lines(await store.list_turns(call.id))
    return "\n".join(lines) + "\n"
