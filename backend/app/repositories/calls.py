"""Queries for sessions, calls, turns and metrics. Queries only: no business rules here.

`CallStore` is the interface; `SqlCallStore` talks to Postgres and `MemoryCallStore` backs
fast tests. Callers generate UUIDs themselves so writes can run in the background.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Call, SandboxSession, Turn, TurnMetrics


@dataclass(frozen=True)
class SessionInfo:
    id: uuid.UUID
    ip_hash: str
    expires_at: datetime


@dataclass(frozen=True)
class TurnRow:
    index: int
    role: str
    text: str
    interrupted: bool


class CallStore(Protocol):
    async def create_session(
        self, session_id: uuid.UUID, token_hash: str, ip_hash: str, expires_at: datetime
    ) -> None: ...
    async def find_session(self, token_hash: str) -> SessionInfo | None: ...
    async def count_sessions_since(self, ip_hash: str, since: datetime) -> int: ...
    async def count_calls_since(self, ip_hash: str, since: datetime) -> int: ...
    async def create_call(self, call_id: uuid.UUID, session_id: uuid.UUID, voice: str) -> None: ...
    async def open_call_for_session(self, call_id: uuid.UUID, session_id: uuid.UUID) -> bool: ...
    async def list_turns(self, call_id: uuid.UUID) -> list[TurnRow]: ...
    async def add_turn(
        self,
        turn_id: uuid.UUID,
        call_id: uuid.UUID,
        index: int,
        role: str,
        text: str,
        interrupted: bool = False,
    ) -> None: ...
    async def update_turn(self, turn_id: uuid.UUID, text: str, interrupted: bool) -> None: ...
    async def save_metrics(
        self, turn_id: uuid.UUID, stages: dict[str, int | None], total_ms: int
    ) -> None: ...
    async def end_call(
        self, call_id: uuid.UUID, outcome: str, summary: str, turn_count: int
    ) -> None: ...


class SqlCallStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def create_session(
        self, session_id: uuid.UUID, token_hash: str, ip_hash: str, expires_at: datetime
    ) -> None:
        async with self._sessionmaker() as db:
            db.add(
                SandboxSession(
                    id=session_id, token_hash=token_hash, ip_hash=ip_hash, expires_at=expires_at
                )
            )
            await db.commit()

    async def find_session(self, token_hash: str) -> SessionInfo | None:
        async with self._sessionmaker() as db:
            row = await db.scalar(
                select(SandboxSession).where(SandboxSession.token_hash == token_hash)
            )
            if row is None:
                return None
            return SessionInfo(row.id, row.ip_hash, row.expires_at)

    async def count_sessions_since(self, ip_hash: str, since: datetime) -> int:
        async with self._sessionmaker() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(SandboxSession)
                .where(SandboxSession.ip_hash == ip_hash, SandboxSession.created_at >= since)
            )
            return int(count or 0)

    async def count_calls_since(self, ip_hash: str, since: datetime) -> int:
        async with self._sessionmaker() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(Call)
                .join(SandboxSession, Call.session_id == SandboxSession.id)
                .where(SandboxSession.ip_hash == ip_hash, Call.started_at >= since)
            )
            return int(count or 0)

    async def create_call(self, call_id: uuid.UUID, session_id: uuid.UUID, voice: str) -> None:
        async with self._sessionmaker() as db:
            db.add(Call(id=call_id, session_id=session_id, voice_mode=voice))
            await db.commit()

    async def open_call_for_session(self, call_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        async with self._sessionmaker() as db:
            found = await db.scalar(
                select(Call.id).where(
                    Call.id == call_id, Call.session_id == session_id, Call.ended_at.is_(None)
                )
            )
            return found is not None

    async def list_turns(self, call_id: uuid.UUID) -> list[TurnRow]:
        async with self._sessionmaker() as db:
            rows = await db.scalars(
                select(Turn).where(Turn.call_id == call_id).order_by(Turn.index)
            )
            return [TurnRow(t.index, t.role, t.text, t.interrupted) for t in rows]

    async def add_turn(
        self,
        turn_id: uuid.UUID,
        call_id: uuid.UUID,
        index: int,
        role: str,
        text: str,
        interrupted: bool = False,
    ) -> None:
        async with self._sessionmaker() as db:
            db.add(
                Turn(
                    id=turn_id,
                    call_id=call_id,
                    index=index,
                    role=role,
                    text=text,
                    interrupted=interrupted,
                )
            )
            await db.commit()

    async def update_turn(self, turn_id: uuid.UUID, text: str, interrupted: bool) -> None:
        async with self._sessionmaker() as db:
            await db.execute(
                update(Turn).where(Turn.id == turn_id).values(text=text, interrupted=interrupted)
            )
            await db.commit()

    async def save_metrics(
        self, turn_id: uuid.UUID, stages: dict[str, int | None], total_ms: int
    ) -> None:
        async with self._sessionmaker() as db:
            await db.merge(TurnMetrics(turn_id=turn_id, total_ms=total_ms, **stages))
            await db.commit()

    async def end_call(
        self, call_id: uuid.UUID, outcome: str, summary: str, turn_count: int
    ) -> None:
        async with self._sessionmaker() as db:
            await db.execute(
                update(Call)
                .where(Call.id == call_id)
                .values(
                    ended_at=datetime.now(UTC),
                    outcome=outcome,
                    summary=summary,
                    turn_count=turn_count,
                )
            )
            await db.commit()


@dataclass
class MemoryCallStore:
    """In-memory CallStore for tests. Mirrors the SQL behavior that the app relies on."""

    sessions: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    calls: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    turns: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)

    async def create_session(
        self, session_id: uuid.UUID, token_hash: str, ip_hash: str, expires_at: datetime
    ) -> None:
        self.sessions[session_id] = {
            "token_hash": token_hash,
            "ip_hash": ip_hash,
            "expires_at": expires_at,
            "created_at": datetime.now(UTC),
        }

    async def find_session(self, token_hash: str) -> SessionInfo | None:
        for sid, s in self.sessions.items():
            if s["token_hash"] == token_hash:
                return SessionInfo(sid, s["ip_hash"], s["expires_at"])
        return None

    async def count_sessions_since(self, ip_hash: str, since: datetime) -> int:
        return sum(
            1
            for s in self.sessions.values()
            if s["ip_hash"] == ip_hash and s["created_at"] >= since
        )

    async def count_calls_since(self, ip_hash: str, since: datetime) -> int:
        return sum(
            1
            for c in self.calls.values()
            if self.sessions[c["session_id"]]["ip_hash"] == ip_hash and c["started_at"] >= since
        )

    async def create_call(self, call_id: uuid.UUID, session_id: uuid.UUID, voice: str) -> None:
        self.calls[call_id] = {
            "session_id": session_id,
            "voice": voice,
            "started_at": datetime.now(UTC),
            "ended_at": None,
            "outcome": None,
            "summary": None,
            "turn_count": 0,
        }

    async def open_call_for_session(self, call_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        call = self.calls.get(call_id)
        return call is not None and call["session_id"] == session_id and call["ended_at"] is None

    async def list_turns(self, call_id: uuid.UUID) -> list[TurnRow]:
        rows = [t for t in self.turns.values() if t["call_id"] == call_id]
        return [
            TurnRow(t["index"], t["role"], t["text"], t["interrupted"])
            for t in sorted(rows, key=lambda t: t["index"])
        ]

    async def add_turn(
        self,
        turn_id: uuid.UUID,
        call_id: uuid.UUID,
        index: int,
        role: str,
        text: str,
        interrupted: bool = False,
    ) -> None:
        self.turns[turn_id] = {
            "call_id": call_id,
            "index": index,
            "role": role,
            "text": text,
            "interrupted": interrupted,
        }

    async def update_turn(self, turn_id: uuid.UUID, text: str, interrupted: bool) -> None:
        self.turns[turn_id].update(text=text, interrupted=interrupted)

    async def save_metrics(
        self, turn_id: uuid.UUID, stages: dict[str, int | None], total_ms: int
    ) -> None:
        self.metrics[turn_id] = {**stages, "total_ms": total_ms}

    async def end_call(
        self, call_id: uuid.UUID, outcome: str, summary: str, turn_count: int
    ) -> None:
        self.calls[call_id].update(
            ended_at=datetime.now(UTC), outcome=outcome, summary=summary, turn_count=turn_count
        )
