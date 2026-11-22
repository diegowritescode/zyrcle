"""Turns payout outbox rows into Treasury transactions.

Each row is claimed (status `submitting`) and committed before the transaction is sent, so a slow
chain never holds database locks. If the process dies mid-send, the row stays `submitting`; the
recovery step asks the contract whether the advance was paid (`advanceOf`) and settles the row
either way. The contract also refuses a second advance for the same deposit, so retries can never
pay twice.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .chain import Chain, TxFailed
from .models import Payout
from .notifications import notify_payout

log = logging.getLogger(__name__)

# Contract errors that mean "not now" rather than "never".
DEFERRABLE = {"DailyCapExceeded", "UnbackedMint", "EnforcedPause"}
STUCK_AFTER = timedelta(minutes=2)


def _next_utc_midnight(now: datetime) -> datetime:
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)


class PayoutWorker:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        chain: Chain,
        oracle,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._maker = maker
        self._chain = chain
        self._oracle = oracle
        self._now = clock

    async def run_once(self, batch: int = 10) -> int:
        await self._recover_stuck()
        claimed = await self._claim(batch)
        for payout_id, session_id, address, amount in claimed:
            await self._pay(payout_id, session_id, address, amount)
        return len(claimed)

    async def _claim(self, batch: int) -> list[tuple[uuid.UUID, uuid.UUID, str, int]]:
        now = self._now()
        async with self._maker() as db:
            rows = list(
                await db.scalars(
                    select(Payout)
                    .where(
                        Payout.status.in_(["pending", "deferred"]),
                        or_(Payout.next_attempt_at.is_(None), Payout.next_attempt_at <= now),
                    )
                    .order_by(Payout.created_at)
                    .limit(batch)
                    .with_for_update(skip_locked=True)
                )
            )
            for p in rows:
                p.status, p.attempts, p.updated_at = "submitting", p.attempts + 1, now
            await db.commit()
            return [(p.id, p.session_id, p.resident_address, p.amount_cop) for p in rows]

    async def _pay(self, payout_id, session_id, address, amount) -> None:
        tx_hash, status, error, retry_at = None, "confirmed", None, None
        try:
            if await self._chain.advance_of(session_id) > 0:
                log.info("advance for %s was already on chain", session_id)
            else:
                tx_hash = await self._chain.pay_advance(self._oracle, session_id, address, amount)
        except TxFailed as e:
            error = str(e)
            if e.error == "AdvanceAlreadyPaid":
                status = "confirmed"
            elif e.error in DEFERRABLE:
                status = "deferred"
                now = self._now()
                retry_at = (
                    _next_utc_midnight(now)
                    if e.error == "DailyCapExceeded"
                    else now + timedelta(minutes=10)
                )
            else:
                status = "failed"
        except Exception as e:  # network trouble: try again shortly
            status, error, retry_at = (
                "pending",
                f"{type(e).__name__}: {e}",
                self._now() + timedelta(seconds=30),
            )
        async with self._maker() as db:
            p = await db.get(Payout, payout_id, with_for_update=True)
            assert p is not None
            p.status, p.last_error, p.next_attempt_at = status, error, retry_at
            p.tx_hash = tx_hash or p.tx_hash
            p.updated_at = self._now()
            if status == "confirmed":
                await notify_payout(db, p, p.updated_at)
            await db.commit()
        log.info("payout %s for session %s: %s %s", payout_id, session_id, status, error or tx_hash)

    async def _recover_stuck(self) -> None:
        cutoff = self._now() - STUCK_AFTER
        async with self._maker() as db:
            stuck = list(
                await db.scalars(
                    select(Payout)
                    .where(Payout.status == "submitting", Payout.updated_at < cutoff)
                    .with_for_update(skip_locked=True)
                )
            )
            for p in stuck:
                try:
                    paid = await self._chain.advance_of(p.session_id) > 0
                except Exception:
                    continue
                p.status = "confirmed" if paid else "pending"
                p.updated_at = self._now()
                if paid:
                    await notify_payout(db, p, p.updated_at)
            await db.commit()
