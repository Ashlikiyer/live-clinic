from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ClinicInfo


@dataclass(frozen=True)
class InfoEntry:
    topic: str
    question: str
    answer: str


class ClinicInfoRepository:
    """The fixed knowledge file behind get_clinic_info. Read-only and cached."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._entries: list[InfoEntry] | None = None

    async def entries(self) -> list[InfoEntry]:
        if self._entries is None:
            async with self._sessionmaker() as db:
                rows = await db.scalars(select(ClinicInfo).order_by(ClinicInfo.id))
                self._entries = [InfoEntry(r.topic, r.question, r.answer) for r in rows]
        return self._entries
