"""One CallSession per WebSocket: receives caller events, runs turns, sends events back."""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import anyio
from fastapi import WebSocket, WebSocketDisconnect, status

from app.agent.context import CallToolState
from app.agent.prompt import GREETING, LLM_RECOVERY_LINE, RECONNECT_LINE, TIME_LIMIT_LINE
from app.call.busy import BUSY_NOTICE, line_is_busy
from app.call.interrupt import History
from app.call.metrics import TurnTiming, call_stats
from app.call.sentences import split_sentences
from app.call.speech import MAX_SPEECH_REQUESTS_PER_CALL, speech_allowed
from app.call.turn import run_turn
from app.core.config import Settings
from app.core.errors import ErrorCode
from app.providers.base import ProviderError, Providers, busy_seconds
from app.providers.tts_cache import FIXED_LINES
from app.repositories.booking import BookingRepository
from app.repositories.calls import CallStore, SessionInfo
from app.repositories.clinic import ClinicInfoRepository
from app.schemas.events import (
    AudioFrameError,
    CallEnd,
    CallStart,
    TextMessage,
    TtsFirstAudio,
    TtsRequest,
    UserInterrupt,
    build_audio_frame,
    now_ms,
    parse_audio_frame,
    parse_client_event,
    server_event,
)

log = logging.getLogger(__name__)

FLUSH_TIMEOUT_S = 5.0


@dataclass
class TurnRecord:
    """Server bookkeeping for one assistant reply."""

    timing: TurnTiming
    db_turn_id: uuid.UUID | None = None
    metrics_sent: bool = False
    metrics_payload: dict[str, Any] | None = None
    # Audit rows for tool_calls, saved once the assistant turn row exists.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ToolDeps:
    booking: BookingRepository
    clinic: ClinicInfoRepository


class CallSession:
    def __init__(
        self,
        websocket: WebSocket,
        session: SessionInfo,
        store: CallStore,
        providers: Providers,
        settings: Settings,
        tools: ToolDeps | None = None,
    ) -> None:
        self.ws = websocket
        self.tools = tools
        self.tool_state = CallToolState()
        self.session = session
        self.store = store
        self.providers = providers
        self.settings = settings
        self.tz = ZoneInfo(settings.clinic_timezone)

        self.call_id: uuid.UUID | None = None
        self.history = History()
        self.turns: dict[int, TurnRecord] = {}
        self.last_turn_id = -1
        self.turn_index = 0
        self.clock_offset_ms = 0
        self.started_monotonic = time.monotonic()
        self.ended = False
        self.outcome: str | None = None
        self.voice = "kokoro"
        self.speech_requests = 0
        # Replies that failed on Groq's rate limit in a row (see app/call/busy.py).
        self.rate_limited_in_a_row = 0

        self._send_lock = asyncio.Lock()
        self._current: asyncio.Task[None] | None = None
        self._current_turn_id: int | None = None
        self._db_queue: asyncio.Queue[Callable[[], Awaitable[None]] | None] = asyncio.Queue()
        self._db_worker: asyncio.Task[None] | None = None
        self._time_limit: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[None]] = set()
        # Speech streams from Groq; stopped when the call ends so they don't use up the quota.
        self._speech: set[asyncio.Task[None]] = set()

    # ---------- plumbing ----------

    async def send(self, type_: str, **payload: Any) -> None:
        if self.ended and type_ not in {"call.ended", "error"}:
            return
        async with self._send_lock:
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await self.ws.send_json(server_event(type_, **payload))

    async def send_bytes(self, frame: bytes) -> None:
        if self.ended:
            return
        async with self._send_lock:
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await self.ws.send_bytes(frame)

    async def send_error(self, code: ErrorCode, message: str, retryable: bool) -> None:
        await self.send("error", code=code.value, message=message, retryable=retryable)

    def db(self, op: Callable[[], Awaitable[None]]) -> None:
        """Queue a database write. Writes run in order, off the latency-critical path."""
        self._db_queue.put_nowait(op)

    async def _run_db_writes(self) -> None:
        while (op := await self._db_queue.get()) is not None:
            try:
                await op()
            except Exception:
                log.exception("Database write failed")

    async def _flush_db(self) -> None:
        if self._db_worker is None:
            return
        self._db_queue.put_nowait(None)
        await self._db_worker
        self._db_worker = None

    def next_turn_id(self, requested: int | None = None) -> int:
        """Server-authoritative turn ids: always increasing, honoring the client's if higher."""
        turn_id = max(self.last_turn_id + 1, requested if requested is not None else -1)
        self.last_turn_id = turn_id
        return turn_id

    def save_turn(self, role: str, text: str, interrupted: bool = False) -> uuid.UUID:
        assert self.call_id is not None
        turn_uuid = uuid.uuid4()
        call_id, index = self.call_id, self.turn_index
        self.turn_index += 1
        self.db(lambda: self.store.add_turn(turn_uuid, call_id, index, role, text, interrupted))
        return turn_uuid

    # ---------- main loop ----------

    async def run(self) -> None:
        self._db_worker = asyncio.create_task(self._run_db_writes())
        try:
            while not self.ended:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await self._on_audio(message["bytes"])
                elif message.get("text") is not None:
                    await self._on_text(message["text"])
        except WebSocketDisconnect:
            pass
        finally:
            # Even if this task is being cancelled (server shutdown, test client closing),
            # finish the queued database writes so the last turns aren't lost. Capped at 5 s.
            with anyio.CancelScope(shield=True), anyio.move_on_after(FLUSH_TIMEOUT_S):
                await self._cancel_current()
                if self._time_limit:
                    self._time_limit.cancel()
                for task in list(self._speech):
                    task.cancel()
                await self._flush_db()

    async def _on_text(self, raw: str) -> None:
        event = parse_client_event(raw)
        if event is None:
            return
        if isinstance(event, CallStart):
            await self._on_call_start(event)
        elif self.call_id is None:
            return
        elif isinstance(event, TextMessage):
            timing = TurnTiming(turn_id=-1, client_start_ts=event.ts, received_at=now_ms())
            await self._start_turn(None, text=event.text.strip(), wav=None, timing=timing)
        elif isinstance(event, TtsRequest):
            await self._on_speech_request(event)
        elif isinstance(event, UserInterrupt):
            await self._on_interrupt(event)
        elif isinstance(event, TtsFirstAudio):
            self._on_first_audio(event)
        elif isinstance(event, CallEnd):
            if event.reason == "silence":
                await self.end(
                    self._default_outcome(), "The caller went silent; Mia ended the call."
                )
            else:
                await self.end(self._default_outcome(), "The caller ended the call.")

    async def _on_audio(self, frame: bytes) -> None:
        if self.call_id is None:
            return
        try:
            header, wav = parse_audio_frame(frame)
        except AudioFrameError as exc:
            log.info("Rejected audio frame: %s", exc)
            return
        timing = TurnTiming(
            turn_id=-1,
            client_start_ts=header.speech_end_ts,
            vad_wait_ms=header.vad_wait_ms,
            received_at=now_ms(),
        )
        await self._start_turn(header.turn_id, text=None, wav=wav, timing=timing)

    # ---------- call lifecycle ----------

    async def _on_call_start(self, event: CallStart) -> None:
        if self.call_id is not None:
            return
        if event.ts is not None:
            self.clock_offset_ms = now_ms() - event.ts
        self.voice = event.voice

        resumed = False
        if event.resume_call_id:
            with contextlib.suppress(ValueError):
                candidate = uuid.UUID(event.resume_call_id)
                if await self.store.open_call_for_session(candidate, self.session.id):
                    self.call_id = candidate
                    resumed = True
                    await self._restore_history()

        if not resumed and line_is_busy(busy_seconds(self.providers.llm)):
            # Every Groq model is at its limit: say so now instead of greeting a caller Mia
            # can't answer. No call is created, so it doesn't use up the daily allowance.
            await self.send_error(ErrorCode.RATE_LIMITED, BUSY_NOTICE, retryable=False)
            await self.ws.close(code=status.WS_1013_TRY_AGAIN_LATER)
            self.ended = True
            return

        if not resumed:
            since = datetime.now(UTC) - timedelta(days=1)
            calls_today = await self.store.count_calls_since(self.session.ip_hash, since)
            if calls_today >= self.settings.calls_per_ip_per_day:
                await self.send_error(
                    ErrorCode.CALL_LIMIT_REACHED,
                    "You've reached today's demo call limit. Please try again tomorrow.",
                    retryable=False,
                )
                await self.ws.close(code=status.WS_1008_POLICY_VIOLATION)
                self.ended = True
                return
            self.call_id = uuid.uuid4()
            await self.store.create_call(self.call_id, self.session.id, event.voice)

        now = datetime.now(self.tz)
        await self.send(
            "call.ready",
            call_id=str(self.call_id),
            today=now.date().isoformat(),
            timezone=self.settings.clinic_timezone,
        )
        self._time_limit = asyncio.create_task(self._enforce_time_limit())
        await self.speak(RECONNECT_LINE if resumed else GREETING)

    async def _restore_history(self) -> None:
        assert self.call_id is not None
        rows = await self.store.list_turns(self.call_id)
        turn_id = 0
        for row in rows:
            if row.role == "user":
                turn_id += 1
                self.history.add_user(turn_id, row.text)
            elif row.role == "assistant":
                self.history.add_assistant(turn_id, row.text).interrupted = row.interrupted
        self.turn_index = (rows[-1].index + 1) if rows else 0
        self.last_turn_id = turn_id

    async def _enforce_time_limit(self) -> None:
        await asyncio.sleep(self.settings.max_call_seconds)
        await self._cancel_current()
        await self.speak(TIME_LIMIT_LINE)
        await self.end(self._default_outcome(), "The call reached the 5-minute demo limit.")

    def _default_outcome(self) -> str:
        if self.outcome or self.tool_state.outcome:
            return self.outcome or self.tool_state.outcome or "info_only"
        has_user_turn = any(e.role == "user" for e in self.history.entries)
        return "info_only" if has_user_turn else "abandoned"

    async def end(self, outcome: str, summary: str) -> None:
        if self.ended or self.call_id is None:
            return
        totals = [
            r.metrics_payload["total_ms"]
            for r in self.turns.values()
            if r.metrics_payload is not None
        ]
        stats = call_stats(totals, time.monotonic() - self.started_monotonic)
        if self.tool_state.callback_notes:
            notes = "; ".join(self.tool_state.callback_notes)
            summary = f"{summary} Staff callback requested about: {notes}."
        call_id, count = self.call_id, len(totals)
        self.db(lambda: self.store.end_call(call_id, outcome, summary, count))
        await self.send("call.ended", outcome=outcome, summary=summary, stats=stats)
        self.ended = True
        if self._time_limit and self._time_limit is not asyncio.current_task():
            self._time_limit.cancel()
        with contextlib.suppress(RuntimeError):
            await self.ws.close()

    # ---------- server-side speech (Groq Orpheus) ----------

    async def _on_speech_request(self, event: TtsRequest) -> None:
        tts = self.providers.tts
        said = [e.text for e in self.history.entries if e.role == "assistant"]
        if tts is None or self.voice != "orpheus":
            reason = (ErrorCode.TTS_FAILED, "Server speech isn't on for this call.")
        elif self.speech_requests >= MAX_SPEECH_REQUESTS_PER_CALL:
            reason = (ErrorCode.RATE_LIMITED, "Too many speech requests for one call.")
        elif not speech_allowed(event.text, said, FIXED_LINES):
            reason = (ErrorCode.TTS_FAILED, "Only Mia's own lines can be spoken.")
        else:
            self.speech_requests += 1
            task = asyncio.create_task(self._stream_speech(event.id, event.text))
            self._speech.add(task)
            task.add_done_callback(self._speech.discard)
            return
        await self.send("tts.failed", id=event.id, code=reason[0].value, message=reason[1])

    async def _stream_speech(self, request_id: int, text: str) -> None:
        """Stream Orpheus PCM as binary `tts.audio` frames, then `tts.done` (or `tts.failed`)."""
        tts = self.providers.tts
        assert tts is not None
        seq = 0
        try:
            async for chunk in tts.stream(text):
                header = {
                    "type": "tts.audio",
                    "id": request_id,
                    "seq": seq,
                    "sample_rate": tts.sample_rate,
                }
                await self.send_bytes(build_audio_frame(header, chunk))
                seq += 1
        except ProviderError as exc:
            log.warning("Speech failed: %s", exc)
            await self.send("tts.failed", id=request_id, code=exc.code.value, message=exc.message)
            return
        await self.send("tts.done", id=request_id, chunks=seq)

    # ---------- turns ----------

    async def _cancel_current(self) -> None:
        task = self._current
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._current = None
        self._current_turn_id = None

    async def _start_turn(
        self,
        requested_turn_id: int | None,
        *,
        text: str | None,
        wav: bytes | None,
        timing: TurnTiming,
    ) -> None:
        await self._cancel_current()
        turn_id = self.next_turn_id(requested_turn_id)
        timing.turn_id = turn_id
        timing.clock_offset_ms = self.clock_offset_ms
        self.turns[turn_id] = TurnRecord(timing)
        self._current_turn_id = turn_id
        self._current = asyncio.create_task(self._guarded_turn(turn_id, text=text, wav=wav))

    async def _guarded_turn(self, turn_id: int, *, text: str | None, wav: bytes | None) -> None:
        """A bug in a turn must never leave the caller waiting in silence."""
        try:
            await run_turn(self, turn_id, text=text, wav=wav)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Turn %s failed", turn_id)
            await self.send_error(ErrorCode.LLM_FAILED, "Something went wrong.", retryable=True)
            await self.speak(LLM_RECOVERY_LINE, turn_id)

    async def speak(self, text: str, turn_id: int | None = None) -> int:
        """Say a fixed line (greeting, recovery, goodbye) without calling the LLM."""
        turn_id = self.next_turn_id() if turn_id is None else turn_id
        earlier = self.history.assistant_for(turn_id)
        lead = " " if earlier is not None and earlier.text else ""  # keep apart from earlier text
        await self.send("agent.text.delta", turn_id=turn_id, delta=lead + text)
        for index, sentence in enumerate(split_sentences(text)):
            await self.send("agent.sentence", turn_id=turn_id, index=index, text=sentence)
        await self.send("agent.text.done", turn_id=turn_id)
        self.history.add_assistant(turn_id, text)
        record = self.turns.get(turn_id)
        db_id = self.save_turn("assistant", text)
        if record:
            record.db_turn_id = db_id
            self.persist_metrics(turn_id)
        return turn_id

    async def _on_interrupt(self, event: UserInterrupt) -> None:
        if self._current_turn_id == event.turn_id:
            await self._cancel_current()
        entry = self.history.apply_interrupt(event.turn_id, event.played_text)
        record = self.turns.get(event.turn_id)
        if record is None:
            return
        record.timing.interrupted = True
        record.timing.stop_ms = event.stop_ms
        if entry is not None and record.db_turn_id is not None:
            db_id, text = record.db_turn_id, entry.text
            self.db(lambda: self.store.update_turn(db_id, text, True))
        if not record.metrics_sent and record.timing.client_start_ts is not None:
            await self.send_metrics(event.turn_id)
        elif record.metrics_sent:
            self.persist_metrics(event.turn_id)  # add stop_ms to the saved row

    def _on_first_audio(self, event: TtsFirstAudio) -> None:
        record = self.turns.get(event.turn_id)
        if record is None or record.metrics_sent or record.timing.client_start_ts is None:
            return
        record.timing.tts_ms = event.tts_ms
        record.timing.first_audio_client_ts = event.ts
        task = asyncio.create_task(self.send_metrics(event.turn_id))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def send_metrics(self, turn_id: int) -> None:
        record = self.turns.get(turn_id)
        if record is None or record.metrics_sent:
            return
        record.metrics_sent = True
        payload = record.timing.event_payload()
        record.metrics_payload = payload
        await self.send("metrics.turn", **payload)
        self.persist_metrics(turn_id)

    def save_tool_calls(self, record: TurnRecord) -> None:
        """Audit this turn's tool calls, after its assistant turn row is queued."""
        if self.tools is None or record.db_turn_id is None or not record.tool_calls:
            return
        booking, turn_uuid, calls = self.tools.booking, record.db_turn_id, list(record.tool_calls)
        record.tool_calls.clear()
        self.db(lambda: booking.save_tool_calls(turn_uuid, calls))

    def persist_metrics(self, turn_id: int) -> None:
        """Save metrics once both the payload and the assistant turn row exist."""
        record = self.turns.get(turn_id)
        if record is None or record.metrics_payload is None or record.db_turn_id is None:
            return
        db_id, payload, stop_ms = record.db_turn_id, record.metrics_payload, record.timing.stop_ms
        self.db(
            lambda: self.store.save_metrics(db_id, payload["stages"], payload["total_ms"], stop_ms)
        )
