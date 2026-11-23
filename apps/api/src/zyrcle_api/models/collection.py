"""Collectors, bags, collections, their fills and incidents (docs/adr/0012)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now


class Collector(Base):
    """A participant the operator named a collector (docs/adr/0012). Paid at the same account."""

    __tablename__ = "collector"
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = _now()


BAG_STATUSES = ("open", "sealed", "sold", "settled")


class Bag(Base):
    """A bag with a printed QR, holding one material (docs/adr/0012). `grams` is the sum of what
    the containers' scales measured into it."""

    __tablename__ = "bag"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in BAG_STATUSES) + ")",
            name="bag_status_valid",
        ),
        CheckConstraint("grams >= 0", name="bag_grams_not_negative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    material: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    collector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resident.id"), index=True)
    grams: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = _now()
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


COLLECTION_STATES = ("authorized", "open", "closing", "closed", "expired", "failed")
COLLECTION_ACTIVE = ("authorized", "open", "closing")
_COLLECTION_ACTIVE_SQL = ", ".join(f"'{s}'" for s in COLLECTION_ACTIVE)


class Collection(Base):
    """A collector emptying one container into bags (docs/adr/0012).

    authorized -> open (lid opened) -> closing (collector done, or idle) -> closed (measured)
    authorized -> expired (the container never opened); closing -> failed (never measured)
    """

    __tablename__ = "collection"
    __table_args__ = (
        CheckConstraint(
            "state IN (" + ", ".join(f"'{s}'" for s in COLLECTION_STATES) + ")",
            name="collection_state_valid",
        ),
        Index(
            "one_active_collection_per_container",
            "container_id",
            unique=True,
            postgresql_where=text(f"state IN ({_COLLECTION_ACTIVE_SQL})"),
        ),
        Index("collection_state_idx", "state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    container_id: Mapped[str] = mapped_column(ForeignKey("container.id"), index=True)
    collector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), index=True)
    state: Mapped[str] = mapped_column(String(16))
    # Scale readings: when the lid opened, the latest, and the final one after it closed.
    tare_g: Mapped[int | None] = mapped_column(Integer)
    last_weight_g: Mapped[int | None] = mapped_column(Integer)
    final_g: Mapped[int | None] = mapped_column(Integer)
    # What the container should have weighed when it opened, from its previous collection and the
    # deposits since then. None when there is nothing to compare with yet.
    expected_g: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    last_activity_at: Mapped[datetime] = _now()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CollectionFill(Base):
    """One material taken out of the container during a collection: into a bag, or as residue
    (`bag_id` None). Weighed by the container's scale: `start_g - end_g`, or 0 when that is below
    the scale's noise threshold (`weight_change_g`, docs/adr/0012 amendments)."""

    __tablename__ = "collection_fill"
    __table_args__ = (
        # One material at a time: at most one fill still open per collection.
        Index(
            "one_open_fill_per_collection",
            "collection_id",
            unique=True,
            postgresql_where=text("end_g IS NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection.id"), index=True)
    bag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bag.id"), index=True)
    material: Mapped[str | None] = mapped_column(String(32))  # the bag's; None for residue
    start_g: Mapped[int] = mapped_column(Integer)
    end_g: Mapped[int | None] = mapped_column(Integer)
    grams: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = _now()
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


INCIDENT_KINDS = ("container_balance", "collection_balance", "bag_balance")
INCIDENT_STATUSES = ("open", "resolved")


class Incident(Base):
    """A mass balance that did not hold (docs/adr/0012). Bags named in an open incident are not
    sold or settled until the operator resolves it."""

    __tablename__ = "incident"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in INCIDENT_KINDS) + ")",
            name="incident_kind_valid",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in INCIDENT_STATUSES) + ")",
            name="incident_status_valid",
        ),
        Index("incident_status_idx", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    container_id: Mapped[str | None] = mapped_column(ForeignKey("container.id"))
    collection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection.id"))
    bag_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID), default=list, server_default=text("'{}'")
    )
    expected_g: Mapped[int] = mapped_column(Integer)
    measured_g: Mapped[int] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(254))
    resolution_note: Mapped[str | None] = mapped_column(Text)
