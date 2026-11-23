"""The worker that carries lost-phone recoveries through the chain (docs/adr/0010)."""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .chain import Chain, TxFailed, account_address
from .config import Settings
from .mail import enqueue_email, render_html
from .models import (
    RECOVERY_LIVE,
    AccountRecovery,
    Booking,
    Collector,
    DepositSession,
    Notification,
    PushToken,
    Resident,
)
from .notifications import enqueue
from .recovery import LEASE, _notify_cancelled

log = logging.getLogger(__name__)


class RecoveryWorker:
    """Carries recoveries through the chain. Each step first reads the chain, so a step that ran
    but whose outcome was not saved (a crash, a timeout) is recognised instead of repeated."""

    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        chain: Chain,
        guardian,
        settings: Settings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._maker = maker
        self._chain = chain
        self._guardian = guardian
        self._settings = settings
        self._tz = ZoneInfo(settings.timezone)
        self._now = clock

    async def run_once(self, batch: int = 5) -> int:
        now = self._now()
        async with self._maker() as db:
            rows = list(
                await db.scalars(
                    select(AccountRecovery)
                    .where(
                        AccountRecovery.status.in_(RECOVERY_LIVE),
                        AccountRecovery.next_attempt_at <= now,
                    )
                    .order_by(AccountRecovery.next_attempt_at)
                    .limit(batch)
                    .with_for_update(skip_locked=True)
                )
            )
            claimed = [(r.id, r.status) for r in rows]
            for r in rows:
                r.next_attempt_at, r.attempts = now + LEASE, r.attempts + 1
            await db.commit()
        for rec_id, status in claimed:
            try:
                if status == "starting":
                    await self._start(rec_id)
                elif status == "waiting":
                    await self._finish(rec_id)
                else:
                    await self._cancel(rec_id)
            except TxFailed as e:
                await self._tx_failed(rec_id, e)
            except Exception as e:  # network trouble: try again shortly
                log.warning("recovery %s: %s", rec_id, e)
                await self._later(rec_id, f"{type(e).__name__}: {e}", timedelta(seconds=30))
        return len(claimed)

    async def _load(self, rec_id: uuid.UUID) -> tuple[AccountRecovery, Resident]:
        async with self._maker() as db:
            rec = await db.get(AccountRecovery, rec_id)
            target = await db.get(Resident, rec.resident_id) if rec else None
            assert rec is not None and target is not None
            return rec, target

    async def _start(self, rec_id: uuid.UUID) -> None:
        rec, target = await self._load(rec_id)
        account = rec.account_address
        if not await self._chain.is_deployed(account):
            # Never deployed, so its owner is still its first owner: the key it was predicted from.
            factory = self._settings.account_factory_address
            if not factory or account_address(factory, target.owner_address) != account:
                raise TxFailed("AccountMismatch", f"{account} is not {target.owner_address}'s")
            await self._chain.create_account(self._guardian, target.owner_address)
        pending = await self._chain.pending_recovery(account)
        tx = None
        if pending.new_owner != rec.new_owner:
            tx = await self._chain.start_recovery(self._guardian, account, rec.new_owner)
            pending = await self._chain.pending_recovery(account)
        ready_at = datetime.fromtimestamp(pending.ready_at, UTC)
        async with self._maker() as db:
            rec = await db.get(AccountRecovery, rec_id, with_for_update=True)
            assert rec is not None
            rec.start_tx, rec.ready_at, rec.last_error = tx or rec.start_tx, ready_at, None
            rec.updated_at = self._now()
            if rec.status == "starting":
                rec.status, rec.next_attempt_at = "waiting", ready_at
            elif rec.status == "cancelling":
                rec.next_attempt_at = self._now()
            await db.commit()
        log.info("recovery %s waiting on chain until %s (%s)", rec_id, ready_at, tx)

    async def _finish(self, rec_id: uuid.UUID) -> None:
        rec, _ = await self._load(rec_id)
        tx = None
        if await self._chain.account_owner(rec.account_address) != rec.new_owner:
            pending = await self._chain.pending_recovery(rec.account_address)
            if pending.new_owner != rec.new_owner:
                # Cancelled on chain by the owner itself (a signed message submitted by anyone).
                await self._cancelled(rec_id, None, by="chain")
                return
            tx = await self._chain.finish_recovery(self._guardian, rec.account_address)
        await self._complete(rec_id, tx)

    async def _cancel(self, rec_id: uuid.UUID) -> None:
        rec, _ = await self._load(rec_id)
        tx = None
        if await self._chain.is_deployed(rec.account_address):
            pending = await self._chain.pending_recovery(rec.account_address)
            if pending.new_owner == rec.new_owner:
                tx = await self._chain.cancel_recovery(self._guardian, rec.account_address)
            elif await self._chain.account_owner(rec.account_address) == rec.new_owner:
                await self._complete(rec_id, None)  # too late: the chain already finished it
                return
        await self._cancelled(rec_id, tx, by=None)

    async def _cancelled(self, rec_id: uuid.UUID, tx: str | None, by: str | None) -> None:
        now = self._now()
        async with self._maker() as db:
            rec = await db.get(AccountRecovery, rec_id, with_for_update=True)
            assert rec is not None
            if rec.status not in RECOVERY_LIVE:
                return
            rec.status, rec.cancel_tx, rec.updated_at = "cancelled", tx, now
            rec.cancelled_by = by or rec.cancelled_by
            await _notify_cancelled(db, rec, now)
            await db.commit()
        log.info("recovery %s cancelled (%s)", rec_id, tx)

    async def _complete(self, rec_id: uuid.UUID, tx: str | None) -> None:
        """The account obeys the new key: fold the new phone's resident into it."""
        now = self._now()
        async with self._maker() as db:
            rec = await db.get(AccountRecovery, rec_id, with_for_update=True)
            assert rec is not None
            if rec.status == "done":
                return
            target = await db.get(Resident, rec.resident_id, with_for_update=True)
            assert target is not None
            new_id = rec.new_resident_id
            # The old phones stop getting this account's notifications...
            await db.execute(delete(PushToken).where(PushToken.resident_id == target.id))
            if new_id is not None:
                # ...and the new one starts. Anything the new phone did meanwhile moves too.
                for model in (PushToken, DepositSession, Booking):
                    await db.execute(
                        update(model)
                        .where(model.resident_id == new_id)
                        .values(resident_id=target.id)
                    )
                await db.execute(delete(Notification).where(Notification.resident_id == new_id))
                # A collector role given to the new phone moves to the account (docs/adr/0012).
                if await db.get(Collector, target.id) is None:
                    await db.execute(
                        update(Collector)
                        .where(Collector.resident_id == new_id)
                        .values(resident_id=target.id)
                    )
                await db.execute(delete(Collector).where(Collector.resident_id == new_id))
                rec.new_resident_id = None
                await db.flush()
                await db.execute(delete(Resident).where(Resident.id == new_id))
            target.owner_address = rec.new_owner
            rec.status, rec.finish_tx, rec.updated_at, rec.last_error = "done", tx, now, None
            await db.flush()
            await enqueue(
                db,
                resident_id=target.id,
                kind="recovery_done",
                dedupe_key=f"recovery_done:{rec.id}",
                title="Recuperaste tu cuenta",
                body="Tu saldo, tu historial y tus turnos ya están en este teléfono.",
                data={"url": "/", "recovery_id": str(rec.id)},
                now=now,
            )
            if target.email:
                lines = [
                    "Tu cuenta de Zyrcle ya está en tu teléfono nuevo, con tu saldo y tu "
                    "historial.",
                    "El teléfono anterior ya no puede usarla.",
                ]
                await enqueue_email(
                    db,
                    to=target.email,
                    kind="recovery_done",
                    dedupe_key=f"recovery_done:{rec.id}",
                    subject="Tu cuenta de Zyrcle ya está en tu teléfono nuevo",
                    text="\n\n".join(lines) + "\n",
                    html_body=render_html("Recuperaste tu cuenta", lines),
                    now=now,
                )
            await db.commit()
        log.info("recovery %s done (%s)", rec_id, tx)

    async def _tx_failed(self, rec_id: uuid.UUID, e: TxFailed) -> None:
        if e.error == "RecoveryNotReady":  # chain time is behind ours: try again a bit later
            await self._later(rec_id, str(e), timedelta(minutes=1))
            return
        log.error("recovery %s failed: %s", rec_id, e)
        async with self._maker() as db:
            rec = await db.get(AccountRecovery, rec_id, with_for_update=True)
            assert rec is not None
            rec.status, rec.last_error, rec.updated_at = "failed", str(e), self._now()
            await db.commit()

    async def _later(self, rec_id: uuid.UUID, error: str, after: timedelta) -> None:
        async with self._maker() as db:
            rec = await db.get(AccountRecovery, rec_id, with_for_update=True)
            assert rec is not None
            rec.last_error, rec.next_attempt_at = error, self._now() + after
            await db.commit()
