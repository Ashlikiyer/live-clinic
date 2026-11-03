"""Runs a scenario: a real call over the WebSocket in text mode, then reads the database.

The app runs in-process (Starlette's TestClient) with the configured providers and the real
database. The simulated caller, the judge and the database reads run on a separate event loop
(an anyio blocking portal), so nothing shares connections across loops.
"""

import asyncio
import contextlib
import queue
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.testclient import WebSocketTestSession

from app.core.config import Settings
from app.core.errors import ErrorCode
from app.core.security import hash_token
from app.db.models import Call, IntakeForm, SandboxAppointment, SandboxSession, ToolCall, Turn
from app.providers.base import LLMProvider, ProviderError

from .caller import caller_reply, caller_system_prompt
from .judge import Judgement, judge_call
from .model import (
    Appointment,
    CallRecord,
    EndedBy,
    Event,
    Facts,
    Line,
    Scenario,
    SetupContext,
    ToolAudit,
)

# Seconds to wait for Mia's reply to one caller line (tools + LLM rounds + rate-limit waits).
TURN_TIMEOUT_S = 90.0
# After Mia's reply, how long a hang-up (call.ended) may take to follow it.
END_GRACE_S = 1.0
# After a rate-limit error, wait this long before the caller speaks again.
RATE_LIMIT_BACKOFF_S = 20.0
# The caller and the judge share Groq's free tier too: retry them this often when limited.
PROVIDER_RETRIES = 4

T = TypeVar("T")


@contextlib.contextmanager
def scenario_settings(settings: Settings, mia_fallbacks: str | None) -> Iterator[None]:
    """Lift the per-IP demo limits (every scenario call comes from one IP) and the 5-minute
    cap (pacing makes calls slow); optionally narrow Mia's fallback models. Restored after."""
    changes: dict[str, Any] = {
        "calls_per_ip_per_day": 100_000,
        "sessions_per_ip_per_day": 100_000,
        "max_call_seconds": 1800,
    }
    if mia_fallbacks is not None:
        changes["llm_fallback_models"] = mia_fallbacks
    saved = {name: getattr(settings, name) for name in changes}
    for name, value in changes.items():
        setattr(settings, name, value)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(settings, name, value)


@dataclass
class ScenarioResult:
    scenario: Scenario
    record: CallRecord
    failures: list[str]
    judgement: Judgement | None
    seconds: float
    facts: Facts = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.failures


class _EventReader:
    """Reads server events on a thread, so the runner can wait for them with a timeout."""

    def __init__(self, ws: WebSocketTestSession) -> None:
        self._ws = ws
        self._queue: queue.Queue[Event | None] = queue.Queue()
        self.closed = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            while True:
                self._queue.put(self._ws.receive_json())
        except Exception:  # the socket closed (call.ended, or the runner hung up)
            self._queue.put(None)

    def next(self, timeout: float) -> Event | None:
        """The next event; None once the socket is closed. Raises queue.Empty on timeout."""
        if self.closed:
            return None
        event = self._queue.get(timeout=timeout)
        if event is None:
            self.closed = True
        return event


@dataclass
class _Reply:
    text: str
    events: list[Event]
    ended: bool
    timed_out: bool = False


def _reply_text(events: list[Event], turn_id: int) -> str:
    return "".join(
        str(e["delta"])
        for e in events
        if e["type"] == "agent.text.delta" and e.get("turn_id") == turn_id
    ).strip()


def wait_for_reply(reader: _EventReader, turn_id: int | None, timeout: float) -> _Reply:
    """Collect events until Mia's reply is done, then briefly watch for a hang-up.

    `turn_id` is the reply to wait for; None means "the reply to the caller line just sent",
    whose id arrives in transcript.user.final.
    """
    events: list[Event] = []
    deadline = time.monotonic() + timeout
    target = turn_id
    while True:
        try:
            event = reader.next(max(0.01, deadline - time.monotonic()))
        except queue.Empty:
            return _Reply(_reply_text(events, target or -1), events, False, timed_out=True)
        if event is None:
            return _Reply(_reply_text(events, target or -1), events, True)
        events.append(event)
        if event["type"] == "call.ended":
            return _Reply(_reply_text(events, target or -1), events, True)
        if target is None and event["type"] == "transcript.user.final":
            target = int(event["turn_id"])
        if event["type"] == "agent.text.done" and target is not None:
            if event.get("turn_id") == target:
                break
    ended = False
    grace = time.monotonic() + END_GRACE_S
    while (left := grace - time.monotonic()) > 0:
        try:
            event = reader.next(left)
        except queue.Empty:
            break
        if event is None:
            ended = True
            break
        events.append(event)
        if event["type"] == "call.ended":
            ended = True
            break
    return _Reply(_reply_text(events, target), events, ended)


class ScenarioRunner:
    def __init__(
        self,
        client: TestClient,
        portal: BlockingPortal,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        caller: LLMProvider,
        judge: LLMProvider | None,
        *,
        pace_s: float = 0.0,
        turn_timeout_s: float = TURN_TIMEOUT_S,
        backoff_s: float = RATE_LIMIT_BACKOFF_S,
        log: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.portal = portal
        self.sessionmaker = sessionmaker
        self.settings = settings
        self.tz = ZoneInfo(settings.clinic_timezone)
        self.caller = caller
        self.judge = judge
        self.pace_s = pace_s
        self.turn_timeout_s = turn_timeout_s
        self.backoff_s = backoff_s
        self.log = log
        self._last_send = 0.0

    def run(self, scenario: Scenario) -> ScenarioResult:
        started = time.monotonic()
        response = self.client.post("/api/sessions")
        response.raise_for_status()
        token = str(response.json()["session_token"])
        session_id = self.portal.call(self._session_id, token)
        facts: Facts = {}
        if scenario.setup is not None:
            context = SetupContext(self.sessionmaker, session_id, datetime.now(self.tz), self.tz)
            facts = self.portal.call(scenario.setup, context)

        call_id, transcript, events, ended_by = self._converse(scenario, facts, token)
        record = self.portal.call(self._load_record, call_id, session_id)
        record.transcript, record.events, record.ended_by = transcript, events, ended_by

        failures = scenario.check(record, facts)
        if ended_by == "timeout":
            failures.append("Mia didn't reply in time")
        if ended_by == "rate_limited":
            failures.append("stopped: the caller model stayed rate limited (Groq free tier)")
        judgement = None
        if self.judge is not None:
            try:
                judgement = self._call(judge_call, self.judge, scenario, transcript)
            except ProviderError as exc:
                judgement = Judgement(
                    {}, [(c, False) for c in scenario.judge_checks], error=str(exc)
                )
        return ScenarioResult(
            scenario, record, failures, judgement, time.monotonic() - started, facts
        )

    def _call(self, fn: Callable[..., Awaitable[T]], *args: Any) -> T:
        """Run a caller or judge request on the runner's loop, waiting out rate limits."""
        for attempt in range(PROVIDER_RETRIES):
            try:
                return self.portal.call(fn, *args)
            except ProviderError as exc:
                if exc.code != ErrorCode.RATE_LIMITED or attempt == PROVIDER_RETRIES - 1:
                    raise
                self.log(f"    (caller/judge rate limited; waiting {self.backoff_s:.0f} s)")
                time.sleep(self.backoff_s)
        raise AssertionError("unreachable")

    # ---------- the conversation ----------

    def _pace(self) -> None:
        wait = self.pace_s - (time.monotonic() - self._last_send)
        if wait > 0:
            time.sleep(wait)
        self._last_send = time.monotonic()

    def _converse(
        self, scenario: Scenario, facts: Facts, token: str
    ) -> tuple[uuid.UUID, list[Line], list[Event], EndedBy]:
        system = caller_system_prompt(scenario, facts)
        transcript: list[Line] = []
        events: list[Event] = []
        with self.client.websocket_connect(f"/ws/call?token={token}") as ws:
            reader = _EventReader(ws)
            ws.send_json({"type": "call.start", "voice": "kokoro", "ts": int(time.time() * 1000)})
            greeting = wait_for_reply(reader, 0, self.turn_timeout_s)
            events += greeting.events
            ready = [e for e in greeting.events if e["type"] == "call.ready"]
            if not ready:
                raise RuntimeError(f"The call didn't start: {greeting.events}")
            call_id = uuid.UUID(str(ready[0]["call_id"]))
            transcript.append(Line("mia", greeting.text))
            self.log(f"    Mia: {greeting.text}")

            ended_by: EndedBy = "turn_limit"
            for _ in range(scenario.max_turns):
                try:
                    line = self._call(caller_reply, self.caller, system, transcript)
                except ProviderError:
                    ended_by = "rate_limited"
                    break
                if line.text:
                    transcript.append(Line("caller", line.text))
                    self.log(f"    Caller: {line.text}")
                    self._pace()
                    ws.send_json({"type": "text.message", "text": line.text, "ts": 1})
                    reply = wait_for_reply(reader, None, self.turn_timeout_s)
                    events += reply.events
                    if reply.text:
                        transcript.append(Line("mia", reply.text))
                        self.log(f"    Mia: {reply.text}")
                    if reply.timed_out:
                        ended_by = "timeout"
                        break
                    if reply.ended:
                        ended_by = "agent"
                        break
                    if any(
                        e["type"] == "error" and e.get("code") == "RATE_LIMITED"
                        for e in reply.events
                    ):
                        self.log(f"    (rate limited; waiting {self.backoff_s:.0f} s)")
                        time.sleep(self.backoff_s)
                if line.hangup:
                    if not line.text:
                        self.log(f"    (the caller hung up{': ' + line.note if line.note else ''})")
                    ended_by = "caller"
                    break

            if not reader.closed:
                ws.send_json({"type": "call.end", "reason": "user", "ts": 1})
                events += wait_for_reply(reader, -1, 10.0).events
        return call_id, transcript, events, ended_by

    # ---------- database ----------

    async def _session_id(self, token: str) -> uuid.UUID:
        token_hash = hash_token(self.settings.session_secret, token)
        async with self.sessionmaker() as db:
            session_id = await db.scalar(
                select(SandboxSession.id).where(SandboxSession.token_hash == token_hash)
            )
        if session_id is None:
            raise RuntimeError("The new session wasn't found in the database")
        return session_id

    async def _load_record(self, call_id: uuid.UUID, session_id: uuid.UUID) -> CallRecord:
        """Read the call once its end is saved (writes are queued after each turn)."""
        for _ in range(100):
            async with self.sessionmaker() as db:
                call = await db.get(Call, call_id)
                if call is not None and call.ended_at is not None:
                    break
            await asyncio.sleep(0.1)
        async with self.sessionmaker() as db:
            call = await db.get(Call, call_id)
            rows = await db.scalars(
                select(SandboxAppointment)
                .where(SandboxAppointment.session_id == session_id)
                .order_by(SandboxAppointment.start)
            )
            appointments = [
                Appointment(
                    str(r.id), r.doctor_id, r.start, r.visit_type, r.status, r.replaces_seed_id
                )
                for r in rows
            ]
            form = await db.scalar(select(IntakeForm.data).where(IntakeForm.call_id == call_id))
            audits = await db.scalars(
                select(ToolCall)
                .join(Turn, Turn.id == ToolCall.turn_id)
                .where(Turn.call_id == call_id)
                .order_by(Turn.index)
            )
            tool_calls = [ToolAudit(a.name, a.args, a.result, a.ok) for a in audits]
        return CallRecord(
            call_id=call_id,
            session_id=session_id,
            transcript=[],
            events=[],
            ended_by="turn_limit",
            outcome=call.outcome if call else None,
            appointments=appointments,
            form=dict(form or {}),
            tool_calls=tool_calls,
        )
