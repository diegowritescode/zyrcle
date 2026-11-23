"""The declarative base and helpers every table uses. Weights in integer grams, distances in mm,
volumes in ml."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..domain.session_machine import ACTIVE, State

ACTIVE_SQL = ", ".join(f"'{s.value}'" for s in sorted(ACTIVE))
STATES_SQL = ", ".join(f"'{s.value}'" for s in State)


class Base(DeclarativeBase):
    pass


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
