from enum import StrEnum

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Stable constraint names so Alembic migrations are deterministic.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def in_values(column: str, enum: type[StrEnum]) -> str:
    """SQL for a CHECK constraint limiting a text column to an enum's values."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
