"""Turn runner: speech-to-text -> emergency check -> LLM stream -> tools -> sentences.

The tool loop: stream the LLM reply (text is spoken as it arrives); if it asks for tools, run up
to MAX_TOOLS_PER_ROUND of them, send their UI events, and call the LLM again with the results.
At most MAX_ROUNDS LLM round-trips per caller turn, then apologize and offer a callback.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.agent.context import ToolContext
from app.agent.handlers import run_tool
from app.agent.prompt import (
    ANYTHING_ELSE_LINE,
    BUSY_LINE,
    BUSY_LINE_TL,
    BUSY_SUMMARY,
    GIVE_UP_LINE,
    GOODBYE_LINE,
    LLM_RECOVERY_LINE,
    STT_RECOVERY_LINE,
    build_system_prompt,
)
from app.agent.tools import tool_specs
from app.call.busy import should_hang_up
from app.call.emergency import detect_emergency, emergency_reply, looks_tagalog
from app.call.sentences import MetaTextFilter, SentenceSplitter, is_question
from app.core.errors import ErrorCode
from app.providers.base import ChatMessage, ProviderError, ToolCallRequest, busy_seconds
from app.schemas.events import now_ms

if TYPE_CHECKING:
    from app.call.session import CallSession

MAX_TOOLS_PER_ROUND = 3
MAX_ROUNDS = 4


async def run_turn(
    call: "CallSession", turn_id: int, *, text: str | None, wav: bytes | None
) -> None:
    record = call.turns[turn_id]
    timing = record.timing

    if wav is not None:
        started = time.perf_counter()
        try:
            text = await call.providers.stt.transcribe(wav)
        except ProviderError as exc:
            await call.send_error(exc.code, exc.message, exc.retryable)
            await call.speak(STT_RECOVERY_LINE, turn_id)
            return
        timing.stt_ms = round((time.perf_counter() - started) * 1000)

    text = (text or "").strip()
    if not text:
        # Noise or silence: nothing to answer. The caller can simply speak again.
        return

    await call.send("transcript.user.final", turn_id=turn_id, text=text, stt_ms=timing.stt_ms or 0)
    call.history.add_user(turn_id, text)
    call.save_turn("user", text)

    # Emergency signs override everything, and are checked before the LLM sees the words.
    category = detect_emergency(text)
    if category is not None:
        call.outcome = "emergency_advised"
        await call.speak(emergency_reply(text), turn_id)
        await call.end(
            "emergency_advised",
            f"The caller described possible emergency signs ({category.replace('_', ' ')}) "
            "and was advised to call 911 or go to the nearest emergency room.",
        )
        return

    await _reply(call, turn_id)


def _tool_context(call: "CallSession", turn_id: int) -> ToolContext:
    assert call.tools is not None and call.call_id is not None
    return ToolContext(
        session_id=call.session.id,
        call_id=call.call_id,
        turn_id=turn_id,
        last_user_text=call.history.last_user_text(),
        repo=call.tools.booking,
        clinic=call.tools.clinic,
        llm=call.providers.llm,
        tz=call.tz,
        state=call.tool_state,
    )


async def _reply(call: "CallSession", turn_id: int) -> None:
    record = call.turns[turn_id]
    timing = record.timing
    tools = tool_specs() if call.tools is not None else None
    system = build_system_prompt(datetime.now(call.tz), tools_enabled=tools is not None)
    messages = call.history.to_messages(system)
    entry = call.history.add_assistant(turn_id, "")
    splitter = SentenceSplitter()
    meta = MetaTextFilter()
    index = 0
    # Once Mia asks a question, the rest of the turn's text is dropped (tools still run): one
    # question per turn, and no "answering for the caller" by an over-eager model.
    asked = False

    async def emit(sentence: str) -> None:
        nonlocal index, asked
        if asked:
            return
        if index == 0:
            timing.first_sentence_at = now_ms()
        delta = f" {sentence}" if entry.text else sentence
        entry.text += delta
        await call.send("agent.text.delta", turn_id=turn_id, delta=delta)
        await call.send("agent.sentence", turn_id=turn_id, index=index, text=sentence)
        index += 1
        asked = is_question(sentence)

    async def say(raw: str) -> None:
        if timing.first_token_at is None:
            timing.first_token_at = now_ms()
        for sentence in splitter.feed(meta.feed(raw)):
            await emit(sentence)

    async def flush() -> None:
        if (pending := splitter.flush()) is not None:
            await emit(pending)

    timing.llm_started_at = now_ms()
    try:
        for _ in range(MAX_ROUNDS):
            requests: list[ToolCallRequest] = []
            spoken_before = len(entry.text)
            async for chunk in call.providers.llm.stream(messages, tools):
                if isinstance(chunk, ToolCallRequest):
                    requests.append(chunk)
                else:
                    await say(chunk)
            if not requests:
                break
            # Speak what came before the tool calls ("Let me check.") right away.
            await flush()
            round_text = entry.text[spoken_before:].strip()
            results = await _run_tools(call, turn_id, requests)
            call.history.add_tool_exchange(entry, tuple(requests), results)
            if call.tool_state.end_request is not None and entry.text:
                break  # the goodbye was already said; don't ask the LLM to say it again
            if asked:
                # Mia already asked her question; anything more would be dropped anyway.
                # The tool results stay in the history for the next turn. Saves an LLM call.
                break
            if round_text and _wrapped_up_too_early(requests, results):
                # Mia said her closing lines but the caller isn't done: ask instead of another
                # LLM round, which would repeat them. Saves an LLM call too.
                await say(ANYTHING_ELSE_LINE)
                break
            messages.append(ChatMessage("assistant", round_text, tool_calls=tuple(requests)))
            messages += [ChatMessage("tool", content, tool_call_id=cid) for cid, content in results]
        else:
            await flush()
            asked = False  # the apology must always be heard
            await say(GIVE_UP_LINE)
        await flush()
        if not entry.text:
            # The model returned nothing to say (no text, no tools): never leave the caller in
            # silence, ask them to repeat instead.
            await say(LLM_RECOVERY_LINE)
            await flush()
        await call.send("agent.text.done", turn_id=turn_id)
    except ProviderError as exc:
        if (end := call.tool_state.end_request) is not None:
            # end_call already went through: say goodbye ourselves and hang up as agreed.
            call.tool_state.end_request = None
            await call.speak(GOODBYE_LINE, turn_id)
            call.save_tool_calls(record)  # speak() saved the turn row; audit its tools too
            await call.end(end.outcome, end.summary)
            return
        if not entry.text:
            call.history.entries.remove(entry)
        await call.send_error(exc.code, exc.message, exc.retryable)
        if exc.code == ErrorCode.RATE_LIMITED:
            call.rate_limited_in_a_row += 1
            if should_hang_up(call.rate_limited_in_a_row, busy_seconds(call.providers.llm)):
                # Groq's free tier is out: say so kindly and hang up, rather than apologize
                # again and again.
                busy = BUSY_LINE_TL if looks_tagalog(call.history.last_user_text()) else BUSY_LINE
                await call.speak(busy, turn_id)
                call.save_tool_calls(record)
                await call.end("abandoned", BUSY_SUMMARY)
                return
        await call.speak(LLM_RECOVERY_LINE, turn_id)
        # Tools may have run before the LLM failed (a cancel, a booking): keep their audit.
        call.save_tool_calls(record)
        return
    except asyncio.CancelledError:
        # Barge-in or a newer turn: keep what was generated; the interrupt handler trims it.
        record.db_turn_id = call.save_turn("assistant", entry.text, interrupted=True)
        call.save_tool_calls(record)
        raise

    record.db_turn_id = call.save_turn("assistant", entry.text, entry.interrupted)
    call.save_tool_calls(record)
    call.persist_metrics(turn_id)
    call.rate_limited_in_a_row = 0

    if (end := call.tool_state.end_request) is not None:
        call.tool_state.end_request = None
        await call.end(end.outcome, end.summary)


def _wrapped_up_too_early(requests: list[ToolCallRequest], results: list[tuple[str, str]]) -> bool:
    """end_call was refused because the caller isn't done, and every other tool succeeded."""
    errors = {
        req.name: json.loads(content).get("error")
        for req, (_, content) in zip(requests, results, strict=True)
    }
    return errors.get("end_call") == "CALLER_NOT_DONE" and all(
        error is None for name, error in errors.items() if name != "end_call"
    )


async def _run_tools(
    call: "CallSession", turn_id: int, requests: list[ToolCallRequest]
) -> list[tuple[str, str]]:
    """Run up to MAX_TOOLS_PER_ROUND tools in order; returns (tool_call_id, result JSON)."""
    record = call.turns[turn_id]
    results: list[tuple[str, str]] = []
    for position, request in enumerate(requests):
        if position >= MAX_TOOLS_PER_ROUND:
            skipped: dict[str, Any] = {
                "error": "TOO_MANY_TOOLS",
                "message": f"At most {MAX_TOOLS_PER_ROUND} tools per step. Call it again next.",
            }
            results.append((request.id, json.dumps(skipped)))
            continue
        await call.send("tool.started", turn_id=turn_id, name=request.name)
        run = await run_tool(_tool_context(call, turn_id), request)
        for event_type, payload in run.result.events:
            await call.send(event_type, **payload)
        await call.send(
            "tool.finished", turn_id=turn_id, name=request.name, ok=run.result.ok, ms=run.ms
        )
        record.tool_calls.append(
            {
                "name": request.name,
                "args": run.args,
                "result": run.result.data,
                "ok": run.result.ok,
                "ms": run.ms,
            }
        )
        results.append((request.id, run.content()))
    return results
