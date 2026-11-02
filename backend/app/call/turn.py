"""Turn runner: speech-to-text -> emergency check -> LLM stream -> sentences.

Tools join this loop in Phase 2.
"""

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING

from app.agent.prompt import LLM_RECOVERY_LINE, STT_RECOVERY_LINE, build_system_prompt
from app.call.emergency import EMERGENCY_REPLY, detect_emergency
from app.call.sentences import SentenceSplitter
from app.providers.base import ProviderError
from app.schemas.events import now_ms

if TYPE_CHECKING:
    from app.call.session import CallSession


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
        await call.speak(EMERGENCY_REPLY, turn_id)
        await call.end(
            "emergency_advised",
            f"The caller described possible emergency signs ({category.replace('_', ' ')}) "
            "and was advised to call 911 or go to the nearest emergency room.",
        )
        return

    await _stream_reply(call, turn_id)


async def _stream_reply(call: "CallSession", turn_id: int) -> None:
    record = call.turns[turn_id]
    timing = record.timing
    messages = call.history.to_messages(build_system_prompt(datetime.now(call.tz)))
    entry = call.history.add_assistant(turn_id, "")
    splitter = SentenceSplitter()
    index = 0

    async def emit(sentence: str) -> None:
        nonlocal index
        if index == 0:
            timing.first_sentence_at = now_ms()
        await call.send("agent.sentence", turn_id=turn_id, index=index, text=sentence)
        index += 1

    timing.llm_started_at = now_ms()
    try:
        async for delta in call.providers.llm.stream(messages):
            if timing.first_token_at is None:
                timing.first_token_at = now_ms()
            entry.text += delta
            await call.send("agent.text.delta", turn_id=turn_id, delta=delta)
            for sentence in splitter.feed(delta):
                await emit(sentence)
        if (last := splitter.flush()) is not None:
            await emit(last)
        await call.send("agent.text.done", turn_id=turn_id)
    except ProviderError as exc:
        call.history.entries.remove(entry)
        await call.send_error(exc.code, exc.message, exc.retryable)
        await call.speak(LLM_RECOVERY_LINE, turn_id)
        return
    except asyncio.CancelledError:
        # Barge-in or a newer turn: keep what was generated; the interrupt handler trims it.
        record.db_turn_id = call.save_turn("assistant", entry.text, interrupted=True)
        raise

    record.db_turn_id = call.save_turn("assistant", entry.text, entry.interrupted)
    call.persist_metrics(turn_id)
