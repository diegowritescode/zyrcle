"""Collections: a collector empties a container into bags (docs/adr/0012).

The container's own scale weighs every bag: the collector scans a bag, takes that material out and
taps "done", and the bag gets the difference between two signed readings. Closing the lid takes the
final measurement, links the deposits made since the previous collection to this one, and checks two
mass balances. A balance that does not hold opens an incident.

Like deposit sessions, every change runs in a transaction that locks its row, and commands go to the
container only after the commit. Device messages arrive through `SessionService`, which hands over
those naming a collection instead of a deposit session.
"""

import logging
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from zyrcle_protocol import command, parse_qr

from .config import Settings
from .domain.session_machine import ACTIVE, State
from .errors import Conflict, Forbidden, Invalid, NotFound, Unavailable
from .models import (
    COLLECTION_ACTIVE,
    Bag,
    Collection,
    CollectionFill,
    Collector,
    Container,
    DepositSession,
    Device,
    Incident,
)
from .sessions import code_valid

log = logging.getLogger(__name__)

BAG_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U
BAG_CODE_LENGTH = 8
BAG_QR_PREFIX = "zyrcle://b/"
# Mass balances hold within the larger of these (docs/adr/0012).
TOLERANCE_G = 50
TOLERANCE_RATIO = 0.02
# Deposits whose material is physically inside once their lid closed, paid or not.
MEASURED_STATES = (State.VERIFIED, State.APPROVED, State.REVIEW, State.REJECTED)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def tolerance(expected: int) -> int:
    return max(TOLERANCE_G, round(abs(expected) * TOLERANCE_RATIO))


def balanced(expected: int, measured: int) -> bool:
    return abs(expected - measured) <= tolerance(expected)


def new_bag_code() -> str:
    return "".join(secrets.choice(BAG_CODE_ALPHABET) for _ in range(BAG_CODE_LENGTH))


def bag_qr(code: str) -> str:
    return f"{BAG_QR_PREFIX}{code}"


def parse_bag(text: str) -> str:
    """A bag's code from its QR (`zyrcle://b/<code>`) or typed by hand."""
    code = text.strip()
    if code.lower().startswith(BAG_QR_PREFIX):
        code = code[len(BAG_QR_PREFIX) :]
    code = code.upper()
    if len(code) != BAG_CODE_LENGTH or any(ch not in BAG_CODE_ALPHABET for ch in code):
        raise Invalid("that is not a Zyrcle bag code")
    return code


def bag_view(b: Bag) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "code": b.code,
        "qr": bag_qr(b.code),
        "material": b.material,
        "status": b.status,
        "grams": b.grams,
        "created_at": b.created_at.isoformat(),
        "sealed_at": b.sealed_at.isoformat() if b.sealed_at else None,
    }


def fill_view(f: CollectionFill, bag: Bag | None) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "bag_code": bag.code if bag else None,
        "material": f.material,
        "residue": f.bag_id is None,
        "start_g": f.start_g,
        "end_g": f.end_g,
        "grams": f.grams,
        "done": f.end_g is not None,
    }


class CollectionService:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        settings: Settings,
        link,
        clock: Callable[[], datetime] = utcnow,
    ):
        self._maker = maker
        self._s = settings
        self._link = link
        self._now = clock

    # ------------------------------------------------------------------ collector actions

    async def start(self, collector_id: uuid.UUID, qr: str) -> dict[str, Any]:
        try:
            container_id, code = parse_qr(qr)
        except ValueError as e:
            raise Invalid(str(e)) from None
        now = self._now()
        async with self._maker() as db:
            await self._require_collector(db, collector_id)
            # Locked like a deposit's start, so a deposit and a collection cannot both take it.
            container = await db.get(Container, container_id, with_for_update=True)
            if container is None:
                raise NotFound("unknown container")
            device = await db.get(Device, container.device_id)
            assert device is not None
            if device.last_seen_at is None or device.last_seen_at < now - timedelta(
                seconds=self._s.device_offline_after_s
            ):
                raise Conflict("container is offline")
            if not code_valid(device, code, now):
                raise Forbidden("access code is invalid or expired; scan the container again")
            deposit = await db.scalar(
                select(DepositSession.id).where(
                    DepositSession.container_id == container_id,
                    DepositSession.state.in_([s.value for s in ACTIVE]),
                )
            )
            if deposit is not None:
                raise Conflict("someone is depositing in this container; try again in a minute")
            mine = await db.scalar(
                select(Collection.id).where(
                    Collection.collector_id == collector_id,
                    Collection.state.in_(COLLECTION_ACTIVE),
                )
            )
            if mine is not None:
                raise Conflict("you already have a collection open")
            c = Collection(
                id=uuid.uuid4(),
                container_id=container_id,
                collector_id=collector_id,
                state="authorized",
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )
            db.add(c)
            try:
                await db.commit()
            except IntegrityError:
                raise Conflict("this container is already being emptied") from None
            device_id = container.device_id
        expires = _ms(now + timedelta(seconds=self._s.unlock_ack_timeout_s))
        try:
            await self._link.send(device_id, command("unlock", expires, session_id=str(c.id)))
        except Exception as e:
            log.warning("unlock command for collection %s failed: %s", c.id, e)
            raise Unavailable("could not reach the container; it will expire shortly") from e
        return await self.view(c.id, collector_id)

    async def view(self, collection_id: uuid.UUID, collector_id: uuid.UUID | None) -> dict:
        """The collection as its collector sees it (`collector_id` None: the operator)."""
        async with self._maker() as db:
            c = await db.get(Collection, collection_id)
            if c is None or (collector_id is not None and c.collector_id != collector_id):
                raise NotFound("unknown collection")
            return await self._view(db, c)

    async def add_fill(
        self, collection_id: uuid.UUID, collector_id: uuid.UUID, bag_code: str | None
    ) -> dict[str, Any]:
        """Start taking one material out: into the bag with `bag_code`, or as residue (None)."""
        now = self._now()
        async with self._maker() as db:
            c = await self._locked(db, collection_id, collector_id)
            if c.state != "open":
                raise Conflict("the container is not open")
            if c.last_weight_g is None:
                raise Conflict("waiting for the container's scale; try again in a second")
            open_fill = await db.scalar(
                select(CollectionFill.id).where(
                    CollectionFill.collection_id == c.id, CollectionFill.end_g.is_(None)
                )
            )
            if open_fill is not None:
                raise Conflict("finish the bag in progress first")
            bag = None
            if bag_code is not None:
                code = parse_bag(bag_code)
                bag = await db.scalar(select(Bag).where(Bag.code == code).with_for_update())
                if bag is None:
                    raise NotFound("unknown bag")
                if bag.status != "open":
                    raise Conflict("this bag is already sealed")
                if bag.collector_id not in (None, collector_id):
                    raise Forbidden("this bag belongs to another collector")
                container = await db.get(Container, c.container_id)
                assert container is not None
                if bag.material not in container.accepted_materials:
                    raise Invalid(f"this container holds no {bag.material}")
                bag.collector_id = collector_id
            db.add(
                CollectionFill(
                    id=uuid.uuid4(),
                    collection_id=c.id,
                    bag_id=bag.id if bag else None,
                    material=bag.material if bag else None,
                    start_g=c.last_weight_g,
                    started_at=now,
                )
            )
            c.last_activity_at = c.updated_at = now
            await db.commit()
            return await self._view(db, c)

    async def finish_fill(
        self, collection_id: uuid.UUID, fill_id: uuid.UUID, collector_id: uuid.UUID
    ) -> dict[str, Any]:
        async with self._maker() as db:
            c = await self._locked(db, collection_id, collector_id)
            fill = await db.get(CollectionFill, fill_id, with_for_update=True)
            if fill is None or fill.collection_id != c.id:
                raise NotFound("unknown bag in this collection")
            if fill.end_g is not None:
                return await self._view(db, c)  # already done: tapping twice is harmless
            if c.state != "open":
                raise Conflict("the container is not open")
            await self._close_fill(db, c, fill)
            await db.commit()
            return await self._view(db, c)

    async def finish(self, collection_id: uuid.UUID, collector_id: uuid.UUID) -> dict[str, Any]:
        async with self._maker() as db:
            c = await self._locked(db, collection_id, collector_id)
            if c.state != "open":
                raise Conflict("the container is not open")
            await self._close_open_fill(db, c)
            c.state, c.updated_at = "closing", self._now()
            device_id = await self._device_of(db, c)
            await db.commit()
        await self._send_lock(device_id, collection_id)
        return await self.view(collection_id, collector_id)

    async def seal_bag(self, bag_code: str, collector_id: uuid.UUID) -> dict[str, Any]:
        code = parse_bag(bag_code)
        async with self._maker() as db:
            bag = await db.scalar(select(Bag).where(Bag.code == code).with_for_update())
            if bag is None or bag.collector_id != collector_id:
                raise NotFound("unknown bag")
            if bag.status == "sealed":
                return bag_view(bag)
            if bag.status != "open":
                raise Conflict("this bag was already sold")
            filling = await db.scalar(
                select(CollectionFill.id).where(
                    CollectionFill.bag_id == bag.id, CollectionFill.end_g.is_(None)
                )
            )
            if filling is not None:
                raise Conflict("this bag is still being filled")
            if bag.grams <= 0:
                raise Conflict("this bag is empty")
            bag.status, bag.sealed_at = "sealed", self._now()
            await db.commit()
            return bag_view(bag)

    async def my_bags(self, collector_id: uuid.UUID) -> list[dict[str, Any]]:
        async with self._maker() as db:
            rows = await db.scalars(
                select(Bag)
                .where(Bag.collector_id == collector_id, Bag.status.in_(["open", "sealed"]))
                .order_by(Bag.status, Bag.created_at)
            )
            return [bag_view(b) for b in rows]

    async def current(self, collector_id: uuid.UUID) -> dict[str, Any] | None:
        """The collector's collection still in progress, if any."""
        async with self._maker() as db:
            c = await db.scalar(
                select(Collection).where(
                    Collection.collector_id == collector_id,
                    Collection.state.in_(COLLECTION_ACTIVE),
                )
            )
            return await self._view(db, c) if c else None

    # ------------------------------------------------------------------ device messages

    async def find(self, db: AsyncSession, raw_id: Any, device_id: str) -> Collection | None:
        try:
            collection_id = uuid.UUID(str(raw_id))
        except ValueError:
            return None
        c = await db.get(Collection, collection_id, with_for_update=True)
        if c is None:
            return None
        container = await db.get(Container, c.container_id)
        if container is None or container.device_id != device_id:
            log.warning("device %s reported on a collection of another container", device_id)
            return None
        return c

    async def on_event(self, db: AsyncSession, c: Collection, body: dict, now: datetime) -> None:
        if body.get("name") != "lock_opened" or c.state != "authorized":
            return
        weight = _int(body.get("weight_g"))
        c.state, c.tare_g, c.last_weight_g = "open", weight, weight
        c.updated_at = c.last_activity_at = now
        c.expected_g = await self._expected(db, c)
        if weight is not None and c.expected_g is not None and not balanced(c.expected_g, weight):
            db.add(
                Incident(
                    id=uuid.uuid4(),
                    kind="container_balance",
                    status="open",
                    container_id=c.container_id,
                    collection_id=c.id,
                    bag_ids=[],
                    expected_g=c.expected_g,
                    measured_g=weight,
                    detail={"tolerance_g": tolerance(c.expected_g)},
                    created_at=now,
                )
            )

    async def on_reading(self, db: AsyncSession, c: Collection, body: dict, now: datetime) -> None:
        weight = _int(body.get("weight_g"))
        if weight is None or c.state != "open":
            return
        if c.last_weight_g is None or abs(weight - c.last_weight_g) >= self._s.weight_change_g:
            c.last_activity_at = now
        c.last_weight_g = weight

    async def on_measurement(
        self, db: AsyncSession, c: Collection, body: dict, now: datetime
    ) -> None:
        if c.state != "closing":
            return
        tare, final = _int(body.get("tare_g")), _int(body.get("final_g"))
        if tare is None or final is None:
            return
        c.tare_g, c.final_g, c.last_weight_g = tare, final, final
        c.state, c.closed_at, c.updated_at = "closed", now, now
        fills = list(
            await db.scalars(select(CollectionFill).where(CollectionFill.collection_id == c.id))
        )
        bag_ids = sorted({f.bag_id for f in fills if f.bag_id is not None})
        materials = sorted({f.material for f in fills if f.material is not None})
        # The deposits whose material just left: made here since the previous collection.
        if materials:
            await db.execute(
                update(DepositSession)
                .where(
                    DepositSession.container_id == c.container_id,
                    DepositSession.collection_id.is_(None),
                    DepositSession.created_at < c.created_at,
                    DepositSession.state.in_([s.value for s in MEASURED_STATES]),
                    DepositSession.declared_material.in_(materials),
                )
                .values(collection_id=c.id)
            )
        removed = tare - final
        weighed = sum(f.grams or 0 for f in fills)
        if not balanced(removed, weighed):
            db.add(
                Incident(
                    id=uuid.uuid4(),
                    kind="collection_balance",
                    status="open",
                    container_id=c.container_id,
                    collection_id=c.id,
                    bag_ids=bag_ids,
                    expected_g=removed,
                    measured_g=weighed,
                    detail={"tolerance_g": tolerance(removed)},
                    created_at=now,
                )
            )
        # A container that did not balance when it opened taints the bags filled from it.
        await db.execute(
            update(Incident)
            .where(Incident.collection_id == c.id, Incident.kind == "container_balance")
            .values(bag_ids=bag_ids)
        )

    # ------------------------------------------------------------------ periodic job

    async def sweep(self) -> None:
        now = self._now()
        locks: list[tuple[str, uuid.UUID]] = []
        async with self._maker() as db:
            rules = [
                ("authorized", Collection.created_at, self._s.unlock_ack_timeout_s),
                ("open", Collection.last_activity_at, self._s.collection_idle_timeout_s),
                ("closing", Collection.updated_at, self._s.measurement_timeout_s),
            ]
            for state, column, seconds in rules:
                stale = await db.scalars(
                    select(Collection)
                    .where(Collection.state == state, column < now - timedelta(seconds=seconds))
                    .with_for_update(skip_locked=True)
                )
                for c in stale:
                    if state == "authorized":
                        c.state = "expired"
                        locks.append((await self._device_of(db, c), c.id))
                    elif state == "open":
                        await self._close_open_fill(db, c)
                        c.state = "closing"
                        locks.append((await self._device_of(db, c), c.id))
                    else:
                        c.state = "failed"
                    c.updated_at = now
            await db.commit()
        for device_id, collection_id in locks:
            await self._send_lock(device_id, collection_id)

    # ------------------------------------------------------------------ helpers

    async def _expected(self, db: AsyncSession, c: Collection) -> int | None:
        """What the container should weigh now: what the previous collection left, plus what every
        deposit since then added. Never collected: the tare of its first deposit."""
        previous = await db.scalar(
            select(Collection)
            .where(
                Collection.container_id == c.container_id,
                Collection.state == "closed",
                Collection.id != c.id,
            )
            .order_by(Collection.closed_at.desc())
            .limit(1)
        )
        since = [
            DepositSession.container_id == c.container_id,
            DepositSession.created_at < c.created_at,
            DepositSession.tare_g.is_not(None),
            DepositSession.final_g.is_not(None),
        ]
        if previous is not None:
            since.append(DepositSession.created_at > previous.closed_at)
            base = previous.final_g
        else:
            base = await db.scalar(
                select(DepositSession.tare_g)
                .where(*since)
                .order_by(DepositSession.created_at)
                .limit(1)
            )
        if base is None:
            return None
        added = await db.scalar(
            select(
                func.coalesce(func.sum(DepositSession.final_g - DepositSession.tare_g), 0)
            ).where(*since)
        )
        return base + int(added or 0)

    async def _close_fill(self, db: AsyncSession, c: Collection, fill: CollectionFill) -> None:
        end = c.last_weight_g if c.last_weight_g is not None else fill.start_g
        fill.end_g = end
        # Readings carry a few grams of noise: a bag never weighs less than nothing.
        fill.grams = max(fill.start_g - end, 0)
        fill.done_at = c.last_activity_at = c.updated_at = self._now()
        if fill.bag_id is not None:
            bag = await db.get(Bag, fill.bag_id, with_for_update=True)
            assert bag is not None
            bag.grams += fill.grams

    async def _close_open_fill(self, db: AsyncSession, c: Collection) -> None:
        fill = await db.scalar(
            select(CollectionFill)
            .where(CollectionFill.collection_id == c.id, CollectionFill.end_g.is_(None))
            .with_for_update()
        )
        if fill is not None:
            await self._close_fill(db, c, fill)

    async def _view(self, db: AsyncSession, c: Collection) -> dict[str, Any]:
        container = await db.get(Container, c.container_id)
        assert container is not None
        rows = (
            await db.execute(
                select(CollectionFill, Bag)
                .outerjoin(Bag, Bag.id == CollectionFill.bag_id)
                .where(CollectionFill.collection_id == c.id)
                .order_by(CollectionFill.started_at)
            )
        ).all()
        open_fill = next((f for f, _ in rows if f.end_g is None), None)
        return {
            "id": str(c.id),
            "container_id": c.container_id,
            "container_name": container.name,
            "accepted_materials": container.accepted_materials,
            "state": c.state,
            "tare_g": c.tare_g,
            "weight_g": c.last_weight_g,
            "final_g": c.final_g,
            "expected_g": c.expected_g,
            "removed_g": None if c.final_g is None or c.tare_g is None else c.tare_g - c.final_g,
            "fills": [fill_view(f, b) for f, b in rows],
            "open_fill_id": str(open_fill.id) if open_fill else None,
            "created_at": c.created_at.isoformat(),
            "closed_at": c.closed_at.isoformat() if c.closed_at else None,
        }

    async def _require_collector(self, db: AsyncSession, resident_id: uuid.UUID) -> Collector:
        collector = await db.get(Collector, resident_id)
        if collector is None or not collector.active:
            raise Forbidden("only collectors can empty containers")
        return collector

    async def _locked(
        self, db: AsyncSession, collection_id: uuid.UUID, collector_id: uuid.UUID
    ) -> Collection:
        c = await db.get(Collection, collection_id, with_for_update=True)
        if c is None or c.collector_id != collector_id:
            raise NotFound("unknown collection")
        return c

    async def _device_of(self, db: AsyncSession, c: Collection) -> str:
        container = await db.get(Container, c.container_id)
        assert container is not None
        return container.device_id

    async def _send_lock(self, device_id: str, collection_id: uuid.UUID) -> None:
        expires = _ms(self._now() + timedelta(seconds=self._s.measurement_timeout_s))
        try:
            await self._link.send(
                device_id, command("lock", expires, session_id=str(collection_id))
            )
        except Exception as e:
            log.warning("lock command to %s failed: %s", device_id, e)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
