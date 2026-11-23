"""Deposit sessions: the orchestration around the pure state machine.

Every state change runs inside a database transaction that locks the session row, applies the
transition through `domain.session_machine`, writes an audit event, and commits. Commands to the
container are sent only after the commit, so a device can never act on a session the database has
not stored yet.
"""

import logging
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from zyrcle_protocol import EnvelopeError, command, load_public_key, open_envelope, parse_qr
from zyrcle_protocol.topics import parse_up_topic

from . import bookings
from .config import Settings
from .domain.session_machine import ACTIVE, CREDITED, Event, InvalidTransition, State, transition
from .domain.verification import MAX_BULK_DENSITY_G_PER_ML, Measurement, Outcome, Rules, verify
from .errors import Conflict, Forbidden, Invalid, NotFound, RecoveryPending, Unavailable
from .live import LiveHub
from .models import (
    COLLECTION_ACTIVE,
    Collection,
    Container,
    DepositSession,
    Device,
    DeviceMessage,
    MaterialPrice,
    Payout,
    Resident,
    SessionEvent,
)
from .notifications import notify_session
from .pricing import advance_cop
from .recovery import recovery_pending

log = logging.getLogger(__name__)

CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U
OUTCOME_EVENT = {
    Outcome.OK: Event.MEASURED_OK,
    Outcome.SUSPECT: Event.MEASURED_SUSPECT,
    Outcome.EMPTY: Event.MEASURED_EMPTY,
}


class DeviceLink(Protocol):
    async def send(self, device_id: str, payload: bytes) -> None: ...


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def session_view(s: DepositSession) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "container_id": s.container_id,
        "state": s.state,
        "declared_material": s.declared_material,
        # Scale reading when the lid opened: live readings minus this = what went in so far.
        "tare_g": s.tare_g,
        "deposited_g": s.deposited_g,
        "score": s.score,
        "reasons": s.reasons or [],
        "close_reason": s.close_reason,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }


class SessionService:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        settings: Settings,
        link: DeviceLink,
        hub: LiveHub,
        clock: Callable[[], datetime] = utcnow,
    ):
        self._maker = maker
        self._s = settings
        self._link = link
        self._hub = hub
        self._now = clock
        self._tz = ZoneInfo(settings.timezone)
        self._keys: dict[str, Any] = {}
        self.rejected_messages = 0
        # Device messages that name a collection go there (collection.py, docs/adr/0012).
        self.collections: Any = None

    # ------------------------------------------------------------------ resident actions

    async def start(self, resident_id: uuid.UUID, qr: str, material: str) -> dict[str, Any]:
        try:
            container_id, code = parse_qr(qr)
        except ValueError as e:
            raise Invalid(str(e)) from None
        now = self._now()
        async with self._maker() as db:
            if await recovery_pending(db, resident_id):
                raise RecoveryPending("this phone is waiting to recover an account")
            # Locked so that counting the hour's spots and taking one cannot race (bookings.py).
            container = await db.get(Container, container_id, with_for_update=True)
            if container is None:
                raise NotFound("unknown container")
            device = await db.get(Device, container.device_id)
            assert device is not None
            if not self._online(device, now):
                raise Conflict("container is offline")
            if not code_valid(device, code, now):
                raise Forbidden("access code is invalid or expired; scan the container again")
            if material not in container.accepted_materials:
                raise Invalid(f"this container does not accept {material}")
            emptying = await db.scalar(
                select(Collection.id).where(
                    Collection.container_id == container_id,
                    Collection.state.in_(COLLECTION_ACTIVE),
                )
            )
            if emptying is not None:
                raise Conflict("this container is being emptied; try again in a few minutes")
            busy_elsewhere = await db.scalar(
                select(DepositSession.id).where(
                    DepositSession.resident_id == resident_id,
                    DepositSession.state.in_([s.value for s in ACTIVE]),
                )
            )
            if busy_elsewhere:
                raise Conflict("you already have an open session")
            spot = await bookings.claim_spot(db, resident_id, container, now, self._tz)
            session = DepositSession(
                id=uuid.uuid4(),
                container_id=container_id,
                resident_id=resident_id,
                state=State.AUTHORIZED.value,
                declared_material=material,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )
            db.add(session)
            db.add(
                self._event(
                    session.id,
                    "created",
                    None,
                    State.AUTHORIZED,
                    {"material": material, "booking_id": str(spot.id), "walk_in": spot.walk_in},
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                raise Conflict("container is busy with another resident") from None
            device_id = container.device_id

        expires = _ms(now + timedelta(seconds=self._s.unlock_ack_timeout_s))
        try:
            await self._link.send(device_id, command("unlock", expires, session_id=str(session.id)))
        except Exception as e:
            log.warning("unlock command for %s failed: %s", session.id, e)
            raise Unavailable("could not reach the container; it will expire shortly") from e
        return session_view(session)

    async def finish(self, session_id: uuid.UUID, resident_id: uuid.UUID) -> dict[str, Any]:
        async with self._maker() as db:
            session = await self._locked(db, session_id)
            if session.resident_id != resident_id:
                raise Forbidden("not your session")
            device_id = await self._device_of(db, session)
            outbox: list[tuple[str, dict[str, Any]]] = []
            await self._apply(
                db, session, Event.FINISH_REQUESTED, outbox, close_reason="resident_finished"
            )
            await db.commit()
        self._flush(outbox)
        await self._send_lock(device_id, session.id)
        return session_view(session)

    async def get(self, session_id: uuid.UUID) -> DepositSession:
        async with self._maker() as db:
            session = await db.get(DepositSession, session_id)
            if session is None:
                raise NotFound("unknown session")
            return session

    # ------------------------------------------------------------------ operator actions

    async def review(
        self, session_id: uuid.UUID, approve: bool, reviewer: str, note: str | None
    ) -> dict[str, Any]:
        async with self._maker() as db:
            session = await self._locked(db, session_id)
            session.reviewed_by, session.review_note = reviewer, note
            outbox: list[tuple[str, dict[str, Any]]] = []
            await self._apply(db, session, Event.APPROVED if approve else Event.REJECTED, outbox)
            await db.commit()
        self._flush(outbox)
        return session_view(session)

    async def review_queue(self) -> list[dict[str, Any]]:
        async with self._maker() as db:
            rows = await db.scalars(
                select(DepositSession)
                .where(DepositSession.state == State.REVIEW.value)
                .order_by(DepositSession.updated_at)
            )
            return [session_view(s) for s in rows]

    # ------------------------------------------------------------------ device messages

    async def handle_device_message(self, topic: str, payload: bytes) -> None:
        try:
            device_id, topic_type = parse_up_topic(topic)
        except ValueError:
            self.rejected_messages += 1
            return
        key = await self._public_key(device_id)
        if key is None:
            self.rejected_messages += 1
            log.warning("message from unknown device %s", device_id)
            return
        try:
            env = open_envelope(payload, key)
        except EnvelopeError as e:
            self.rejected_messages += 1
            log.warning("rejected message from %s: %s", device_id, e)
            return
        if env.device_id != device_id or env.type != topic_type:
            self.rejected_messages += 1
            log.warning("envelope/topic mismatch from %s", device_id)
            return

        now = self._now()
        outbox: list[tuple[str, dict[str, Any]]] = []
        async with self._maker() as db:
            device = await db.get(Device, device_id, with_for_update=True)
            assert device is not None
            if env.seq <= device.last_seq:
                return  # duplicate (QoS 1 redelivery) or replay: already handled or never valid
            device.last_seq = env.seq
            device.last_seen_at = now
            db.add(
                DeviceMessage(
                    device_id=device_id, seq=env.seq, type=env.type, device_ts=env.ts, body=env.body
                )
            )
            if env.type == "hello":
                device.firmware = str(env.body.get("fw", ""))[:64]
            elif env.type in ("event", "reading", "measurement"):
                session = await self._session_for_device(db, env.body.get("session_id"), device_id)
                if session is None and self.collections is not None:
                    await self._to_collection(db, env.type, env.body, device_id, now)
                elif session is not None:
                    if env.type == "event":
                        await self._on_event(db, session, env.body, outbox)
                    elif env.type == "reading":
                        await self._on_reading(db, session, env.body, now, outbox)
                    else:
                        await self._on_measurement(db, session, env.body, outbox)
            await db.commit()
        self._flush(outbox)

    async def _to_collection(
        self, db: AsyncSession, kind: str, body: dict, device_id: str, now: datetime
    ) -> None:
        collection = await self.collections.find(db, body.get("session_id"), device_id)
        if collection is None:
            return
        if kind == "event":
            await self.collections.on_event(db, collection, body, now)
        elif kind == "reading":
            await self.collections.on_reading(db, collection, body, now)
        else:
            await self.collections.on_measurement(db, collection, body, now)

    async def _on_event(
        self, db: AsyncSession, session: DepositSession, body: dict, outbox: list
    ) -> None:
        name = body.get("name")
        if name == "lock_opened" and session.state == State.AUTHORIZED.value:
            session.tare_g = _int(body.get("weight_g"))
            session.last_weight_g = session.tare_g
            session.fill_before_mm = _int(body.get("fill_mm"))
            await self._apply(db, session, Event.LOCK_OPENED, outbox, data=body)
        else:
            db.add(self._event(session.id, f"device:{name}", None, None, body))

    async def _on_reading(
        self, db: AsyncSession, session: DepositSession, body: dict, now: datetime, outbox: list
    ) -> None:
        weight = _int(body.get("weight_g"))
        if weight is None or session.state not in (State.OPEN.value, State.DEPOSITING.value):
            return
        outbox.append(
            (
                str(session.id),
                {"type": "reading", "weight_g": weight, "fill_mm": _int(body.get("fill_mm"))},
            )
        )
        moved = session.last_weight_g is None or (
            abs(weight - session.last_weight_g) >= self._s.weight_change_g
        )
        if moved:
            session.last_weight_g = weight
            session.last_activity_at = now
            if (
                session.tare_g is not None
                and abs(weight - session.tare_g) >= self._s.weight_change_g
            ):
                if session.state == State.OPEN.value:
                    await self._apply(
                        db, session, Event.WEIGHT_CHANGED, outbox, data={"weight_g": weight}
                    )

    async def _on_measurement(
        self, db: AsyncSession, session: DepositSession, body: dict, outbox: list
    ) -> None:
        if session.state != State.CLOSING.value:
            db.add(self._event(session.id, "device:late_measurement", None, None, body))
            return
        container = await db.get(Container, session.container_id)
        assert container is not None
        tare, final = _int(body.get("tare_g")), _int(body.get("final_g"))
        before, after = _int(body.get("fill_before_mm")), _int(body.get("fill_after_mm"))
        if None in (tare, final, before, after):
            db.add(self._event(session.id, "device:bad_measurement", None, None, body))
            return
        # Distances are measured from the sensor down to the contents: they shrink as it fills.
        added_ml = max(before - after, 0) * container.area_mm2 // 1000
        uncertainty_ml = 2 * self._s.fill_sensor_noise_mm * container.area_mm2 // 1000
        verdict = verify(
            Measurement(
                declared_material=session.declared_material,
                tare_g=tare,
                final_g=final,
                added_volume_ml=added_ml,
                volume_uncertainty_ml=uncertainty_ml,
                metal_detected=bool(body.get("metal")),
                camera_label=body.get("camera_label"),
            ),
            Rules(),
        )
        session.tare_g, session.final_g = tare, final
        session.fill_before_mm, session.fill_after_mm = before, after
        session.metal_detected = bool(body.get("metal"))
        session.camera_label = body.get("camera_label")
        session.added_volume_ml = added_ml
        session.deposited_g = verdict.deposited_g
        session.score = verdict.score
        session.reasons = verdict.reasons
        await self._apply(db, session, OUTCOME_EVENT[verdict.outcome], outbox, data=body)

    # ------------------------------------------------------------------ periodic jobs

    async def sweep(self) -> None:
        """Time out sessions that stalled. Safe to run on several replicas (SKIP LOCKED)."""
        now = self._now()
        locks: list[tuple[str, uuid.UUID]] = []
        outbox: list[tuple[str, dict[str, Any]]] = []
        rules = [
            (
                State.AUTHORIZED,
                DepositSession.created_at,
                self._s.unlock_ack_timeout_s,
                Event.UNLOCK_TIMEOUT,
                None,
            ),
            (
                State.OPEN,
                DepositSession.last_activity_at,
                self._s.idle_timeout_s,
                Event.IDLE_TIMEOUT,
                "idle",
            ),
            (
                State.DEPOSITING,
                DepositSession.last_activity_at,
                self._s.idle_timeout_s,
                Event.IDLE_TIMEOUT,
                "idle",
            ),
            (
                State.CLOSING,
                DepositSession.updated_at,
                self._s.measurement_timeout_s,
                Event.MEASUREMENT_TIMEOUT,
                None,
            ),
        ]
        async with self._maker() as db:
            for state, column, seconds, event, reason in rules:
                stale = await db.scalars(
                    select(DepositSession)
                    .where(
                        DepositSession.state == state.value,
                        column < now - timedelta(seconds=seconds),
                    )
                    .with_for_update(skip_locked=True)
                )
                for session in stale:
                    await self._apply(db, session, event, outbox, close_reason=reason)
                    if event in (Event.IDLE_TIMEOUT, Event.UNLOCK_TIMEOUT):
                        locks.append((await self._device_of(db, session), session.id))
            await db.commit()
        self._flush(outbox)
        for device_id, session_id in locks:
            await self._send_lock(device_id, session_id)

    async def rotate_codes(self) -> None:
        """Give every online container a fresh access code to show as a QR."""
        now = self._now()
        ttl = timedelta(seconds=2 * self._s.code_rotation_s)
        due = now + timedelta(seconds=self._s.code_rotation_s)
        sends: list[tuple[str, str, datetime]] = []
        async with self._maker() as db:
            devices = await db.scalars(
                select(Device)
                .where(
                    Device.last_seen_at > now - timedelta(seconds=self._s.device_offline_after_s),
                    or_(Device.code_expires_at.is_(None), Device.code_expires_at <= due),
                )
                .with_for_update(skip_locked=True)
            )
            for d in devices:
                d.previous_code, d.previous_code_expires_at = d.current_code, d.code_expires_at
                d.current_code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
                d.code_expires_at = now + ttl
                sends.append((d.id, d.current_code, d.code_expires_at))
            await db.commit()
        for device_id, code, expires in sends:
            try:
                await self._link.send(device_id, command("display", _ms(expires), code=code))
            except Exception as e:
                log.warning("display command to %s failed: %s", device_id, e)

    # ------------------------------------------------------------------ helpers

    async def _apply(
        self,
        db: AsyncSession,
        session: DepositSession,
        event: Event,
        outbox: list[tuple[str, dict[str, Any]]],
        close_reason: str | None = None,
        data: dict | None = None,
    ) -> None:
        current = State(session.state)
        try:
            new = transition(current, event)
        except InvalidTransition as e:
            raise Conflict(str(e)) from None
        session.state = new.value
        session.updated_at = self._now()
        if close_reason and session.close_reason is None:
            session.close_reason = close_reason
        db.add(self._event(session.id, event.value, current, new, data))
        outbox.append((str(session.id), {"type": "state", **session_view(session)}))
        advance_queued = new in CREDITED and await self._queue_advance(db, session)
        # Push the outcomes a resident may no longer be watching (docs/adr/0008). A paid deposit is
        # announced when its payout confirms on chain (payouts.py), not here.
        if new == State.REVIEW:
            await notify_session(db, session, "deposit_review", self._now())
        elif new == State.REJECTED and current == State.REVIEW:
            await notify_session(db, session, "deposit_rejected", self._now())
        elif new == State.APPROVED and not advance_queued:
            await notify_session(db, session, "deposit_approved", self._now())

    async def _queue_advance(self, db: AsyncSession, session: DepositSession) -> bool:
        """Queue the advance in the payout outbox, in the transaction that credits the deposit."""
        price = await db.get(MaterialPrice, session.declared_material)
        amount = advance_cop(
            session.deposited_g or 0,
            price.cop_per_kg if price else 0,
            self._s.advance_ratio_bps,
            self._s.max_advance_cop,
        )
        if amount <= 0:
            db.add(
                self._event(
                    session.id,
                    "no_advance",
                    None,
                    None,
                    {"reason": "no price" if price is None else "amount rounds to 0"},
                )
            )
            return False
        resident = await db.get(Resident, session.resident_id)
        assert resident is not None
        now = self._now()
        db.add(
            Payout(
                id=uuid.uuid4(),
                session_id=session.id,
                kind="advance",
                resident_address=resident.address,
                amount_cop=amount,
                status="pending",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(self._event(session.id, "advance_queued", None, None, {"amount_cop": amount}))
        return True

    def _flush(self, outbox: list[tuple[str, dict[str, Any]]]) -> None:
        """Publish live updates only after the transaction that produced them committed."""
        for session_id, event in outbox:
            self._hub.publish(session_id, event)

    def _event(self, session_id, kind, from_state, to_state, data) -> SessionEvent:
        return SessionEvent(
            session_id=session_id,
            at=self._now(),
            kind=kind,
            from_state=from_state.value if from_state else None,
            to_state=to_state.value if to_state else None,
            data=data,
        )

    async def _locked(self, db: AsyncSession, session_id: uuid.UUID) -> DepositSession:
        session = await db.get(DepositSession, session_id, with_for_update=True)
        if session is None:
            raise NotFound("unknown session")
        return session

    async def _session_for_device(
        self, db: AsyncSession, raw_id: Any, device_id: str
    ) -> DepositSession | None:
        try:
            session_id = uuid.UUID(str(raw_id))
        except ValueError:
            return None
        session = await db.get(DepositSession, session_id, with_for_update=True)
        if session is None:
            return None
        container = await db.get(Container, session.container_id)
        if container is None or container.device_id != device_id:
            log.warning("device %s reported on a session of another container", device_id)
            return None
        return session

    async def _device_of(self, db: AsyncSession, session: DepositSession) -> str:
        container = await db.get(Container, session.container_id)
        assert container is not None
        return container.device_id

    async def _send_lock(self, device_id: str, session_id: uuid.UUID) -> None:
        expires = _ms(self._now() + timedelta(seconds=self._s.measurement_timeout_s))
        try:
            await self._link.send(device_id, command("lock", expires, session_id=str(session_id)))
        except Exception as e:
            log.warning("lock command to %s failed: %s", device_id, e)

    async def _public_key(self, device_id: str):
        if device_id not in self._keys:
            async with self._maker() as db:
                device = await db.get(Device, device_id)
            if device is None:
                return None
            self._keys[device_id] = load_public_key(device.public_key_pem)
        return self._keys[device_id]

    def _online(self, device: Device, now: datetime) -> bool:
        return device.last_seen_at is not None and device.last_seen_at > now - timedelta(
            seconds=self._s.device_offline_after_s
        )


def code_valid(device: Device, code: str, now: datetime) -> bool:
    """Whether `code` is the container's current QR code, or the one before it while it lasts."""
    for value, expires in (
        (device.current_code, device.code_expires_at),
        (device.previous_code, device.previous_code_expires_at),
    ):
        if value and expires and expires > now and secrets.compare_digest(value, code):
            return True
    return False


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


MATERIALS = sorted(MAX_BULK_DENSITY_G_PER_ML)
