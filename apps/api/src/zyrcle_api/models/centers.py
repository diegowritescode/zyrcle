"""Collection centers and the reference price each pays per material (docs/adr/0037)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now

PRICE_SOURCES = ("manual", "sales")


class CollectionCenter(Base):
    """A buyer of sealed bags. Sites sell to one; each sale names the one that bought."""

    __tablename__ = "collection_center"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    tax_id: Mapped[str | None] = mapped_column(String(32))  # NIT
    address: Mapped[str | None] = mapped_column(String(300))
    contact: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = _now()


class CenterPrice(Base):
    """What a center pays per kilogram of a material, used to size advances at the sites that sell
    to it. `sales` when the operator accepted the median of its recent sales."""

    __tablename__ = "center_price"
    __table_args__ = (
        CheckConstraint("cop_per_kg >= 0", name="center_price_cop_per_kg_check"),
        CheckConstraint(
            "source IN (" + ", ".join(f"'{s}'" for s in PRICE_SOURCES) + ")",
            name="center_price_source_valid",
        ),
    )
    center_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_center.id"), primary_key=True
    )
    material: Mapped[str] = mapped_column(String(32), primary_key=True)
    cop_per_kg: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))
    updated_by: Mapped[str] = mapped_column(String(254))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
