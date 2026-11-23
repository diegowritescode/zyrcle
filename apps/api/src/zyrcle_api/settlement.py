"""Settles confirmed sales on chain, one bag at a time (docs/adr/0013).

For each sale line, once its sale is confirmed against the bank: record the sale, pay each credited
deposit in the bag its pro-rata share minus its advance, pay the collector, and pay each host its
part. Every step first asks the chain whether it already happened, so a retry after a crash or a
timeout never pays twice; the contract refuses double payments as well.

A line waits, instead of guessing, while an incident names its bag, a deposit in it is in review,
an advance for one of them is being paid, or a host has no payout address yet.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import any_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .chain import WEI_PER_COP, Chain, TxFailed
from .domain.session_machine import CREDITED, State
from .domain.settlement import parts, pro_rata
from .models import (
    Bag,
    Collection,
    CollectionFill,
    Container,
    DepositSession,
    Host,
    Incident,
    Payout,
    Resident,
    Sale,
    SaleLine,
    Settlement,
    Site,
)
from .notifications import notify_settlement

log = logging.getLogger(__name__)

CHUNK = 40  # deposits per settleResidents transaction
RETRY = timedelta(seconds=30)
STUCK_AFTER = timedelta(minutes=2)
DEFERRABLE = {"UnbackedMint", "EnforcedPause"}


class Wait(Exception):
    """The line cannot settle yet; the message says why."""


@dataclass
class Share:
    party: str  # deposit | collector | host
    ref: str  # session id, collector resident id, host id
    address: str | None
    grams: int
    cop: int


@dataclass
class Plan:
    line: SaleLine
    evidence: bytes
    deposits: list[Share] = field(default_factory=list)
    collector: Share | None = None
    hosts: list[Share] = field(default_factory=list)

    def report(self) -> bytes:
        """sha256 of the settlement report's canonical JSON, anchored on chain with the payments:
        anyone with the report can recompute it."""
        body = {
            "line": str(self.line.id),
            "amount_cop": self.line.amount_cop,
            "shares": [
                [s.party, s.ref, s.address, s.grams, s.cop]
                for s in [
                    *self.deposits,
                    *([self.collector] if self.collector else []),
                    *self.hosts,
                ]
            ],
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).digest()


class SettlementWorker:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        chain: Chain,
        operator,
        oracle,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._maker = maker
        self._chain = chain
        self._operator = operator
        self._oracle = oracle
        self._now = clock

    async def run_once(self, batch: int = 5) -> int:
        claimed = await self._claim(batch)
        for line_id in claimed:
            await self._settle(line_id)
        return len(claimed)

    async def _claim(self, batch: int) -> list[uuid.UUID]:
        now = self._now()
        async with self._maker() as db:
            rows = list(
                await db.scalars(
                    select(SaleLine)
                    .join(Sale, Sale.id == SaleLine.sale_id)
                    .where(
                        Sale.status == "confirmed",
                        or_(
                            SaleLine.status.in_(["pending", "waiting"]),
                            # A worker died mid-way: every step is idempotent, so start over.
                            (SaleLine.status == "settling")
                            & (SaleLine.updated_at < now - STUCK_AFTER),
                        ),
                        or_(SaleLine.next_attempt_at.is_(None), SaleLine.next_attempt_at <= now),
                    )
                    .order_by(SaleLine.created_at)
                    .limit(batch)
                    .with_for_update(of=SaleLine, skip_locked=True)
                )
            )
            for line in rows:
                line.status, line.attempts, line.updated_at = "settling", line.attempts + 1, now
            await db.commit()
            return [line.id for line in rows]

    async def _settle(self, line_id: uuid.UUID) -> None:
        status, reason, retry_at = "settled", None, None
        try:
            async with self._maker() as db:
                plan = await self._plan(db, line_id)
            await self._execute(plan)
        except Wait as w:
            status, reason, retry_at = "waiting", str(w), self._now() + RETRY
        except TxFailed as e:
            if e.error in DEFERRABLE:
                status, reason, retry_at = "waiting", str(e), self._now() + timedelta(minutes=10)
            else:
                status, reason = "failed", str(e)
        except Exception as e:  # network trouble: try again shortly
            status, reason, retry_at = "pending", f"{type(e).__name__}: {e}", self._now() + RETRY
        async with self._maker() as db:
            line = await db.get(SaleLine, line_id, with_for_update=True)
            assert line is not None
            line.status, line.reason, line.next_attempt_at = status, reason, retry_at
            line.updated_at = self._now()
            if status == "settled":
                line.settled_at = self._now()
                bag = await db.get(Bag, line.bag_id, with_for_update=True)
                assert bag is not None
                bag.status = "settled"
                rows = await db.scalars(
                    select(Settlement).where(
                        Settlement.line_id == line_id, Settlement.party == "deposit"
                    )
                )
                for row in rows:
                    await notify_settlement(db, row, self._now())
            await db.commit()
        log.info("sale line %s: %s %s", line_id, status, reason or "")

    # ------------------------------------------------------------------ planning

    async def _plan(self, db: AsyncSession, line_id: uuid.UUID) -> Plan:
        line = await db.get(SaleLine, line_id)
        assert line is not None
        sale = await db.get(Sale, line.sale_id)
        bag = await db.get(Bag, line.bag_id)
        assert sale is not None and bag is not None
        blocking = await db.scalar(
            select(Incident.id).where(Incident.status == "open", any_(Incident.bag_ids) == bag.id)
        )
        if blocking is not None:
            raise Wait("an open incident names this bag")

        fills = list(
            await db.scalars(
                select(CollectionFill).where(
                    CollectionFill.bag_id == bag.id, CollectionFill.end_g.is_not(None)
                )
            )
        )
        collection_ids = sorted({f.collection_id for f in fills})
        sessions = list(
            await db.scalars(
                select(DepositSession)
                .where(
                    DepositSession.collection_id.in_(collection_ids),
                    DepositSession.declared_material == bag.material,
                )
                .order_by(DepositSession.created_at)
            )
        )
        if any(s.state == State.REVIEW.value for s in sessions):
            raise Wait("a deposit in this bag is still in review")
        credited = [
            s
            for s in sessions
            if s.state in {c.value for c in CREDITED} and (s.deposited_g or 0) > 0
        ]
        paying = await db.scalar(
            select(Payout.id).where(
                Payout.session_id.in_([s.id for s in credited]),
                Payout.status.in_(["pending", "submitting"]),
            )
        )
        if paying is not None:
            raise Wait("an advance for a deposit in this bag is being paid")

        shares = await self._chain.shares()
        split = parts(line.amount_cop, shares.residents, shares.collector, shares.host)
        plan = Plan(line=line, evidence=bytes.fromhex(sale.evidence_hash.removeprefix("0x")))

        addresses = dict(
            (
                await db.execute(
                    select(Resident.id, Resident.address).where(
                        Resident.id.in_([s.resident_id for s in credited])
                    )
                )
            ).all()
        )
        amounts = pro_rata(split.residents, [s.deposited_g or 0 for s in credited])
        plan.deposits = [
            Share("deposit", str(s.id), addresses[s.resident_id], s.deposited_g or 0, cop)
            for s, cop in zip(credited, amounts, strict=True)
        ]

        if bag.collector_id is not None:
            collector = await db.get(Resident, bag.collector_id)
            assert collector is not None
            plan.collector = Share(
                "collector", str(collector.id), collector.address, bag.grams, split.collector
            )

        # The hosts whose sites the bag's material came from, by grams.
        by_host: dict[uuid.UUID, int] = {}
        for f in fills:
            host_id = await db.scalar(
                select(Site.host_id)
                .join(Container, Container.site_id == Site.id)
                .join(Collection, Collection.container_id == Container.id)
                .where(Collection.id == f.collection_id)
            )
            by_host[host_id] = by_host.get(host_id, 0) + (f.grams or 0)
        hosts = {h.id: h for h in await db.scalars(select(Host).where(Host.id.in_(list(by_host))))}
        order = sorted(by_host, key=str)
        host_amounts = pro_rata(split.host, [by_host[h] for h in order])
        plan.hosts = [
            Share("host", str(h), hosts[h].payout_address, by_host[h], cop)
            for h, cop in zip(order, host_amounts, strict=True)
        ]
        return plan

    # ------------------------------------------------------------------ execution

    async def _execute(self, plan: Plan) -> None:
        line_id = plan.line.id
        report = plan.report()
        await self._save_shares(plan, report)

        onchain = await self._chain.sale(line_id)
        if not onchain.recorded:
            tx = await self._chain.record_sale(
                self._operator, line_id, plan.line.amount_cop, plan.evidence
            )
            await self._log_tx(line_id, "recordSale", tx)

        pending = [
            s
            for s in plan.deposits
            if s.cop > 0 and not await self._chain.deposit_settled(uuid.UUID(s.ref))
        ]
        for i in range(0, len(pending), CHUNK):
            chunk = pending[i : i + CHUNK]
            tx = await self._chain.settle_residents(
                self._oracle,
                line_id,
                [(uuid.UUID(s.ref), s.address, s.cop) for s in chunk],  # type: ignore[misc]
                report,
            )
            await self._log_tx(line_id, "settleResidents", tx)
            await self._mark_deposits(line_id, chunk, tx)
        # Deposits settled by an earlier attempt whose bookkeeping did not get saved.
        await self._mark_deposits(line_id, [s for s in plan.deposits if s not in pending], None)

        onchain = await self._chain.sale(line_id)
        collector = plan.collector
        if collector is not None and collector.cop > 0:
            owed = collector.cop - onchain.collector_paid // WEI_PER_COP
            tx = None
            if owed > 0:
                tx = await self._chain.pay_collector(self._oracle, line_id, collector.address, owed)  # type: ignore[arg-type]
                await self._log_tx(line_id, "payCollector", tx)
            await self._mark(line_id, collector, collector.cop, tx)

        # Hosts are paid in a fixed order, so what the chain says was paid tells which got theirs.
        paid_before = onchain.host_paid // WEI_PER_COP
        missing: list[str] = []
        for host in plan.hosts:
            if host.cop <= 0:
                continue
            if host.address is None:
                missing.append(host.ref)
                continue
            if paid_before >= host.cop:
                paid_before -= host.cop
                await self._mark(line_id, host, host.cop, None)
                continue
            tx = await self._chain.pay_host(self._oracle, line_id, host.address, host.cop)
            await self._log_tx(line_id, "payHost", tx)
            await self._mark(line_id, host, host.cop, tx)

        async with self._maker() as db:
            line = await db.get(SaleLine, line_id, with_for_update=True)
            assert line is not None
            line.residents_cop = sum(s.cop for s in plan.deposits)
            line.collector_cop = collector.cop if collector else 0
            line.host_cop = sum(h.cop for h in plan.hosts if h.address is not None)
            line.report_hash = "0x" + report.hex()
            await db.commit()
        if missing:
            raise Wait("a host has no payout address yet: " + ", ".join(missing))

    async def _save_shares(self, plan: Plan, report: bytes) -> None:
        rows = [*plan.deposits, *([plan.collector] if plan.collector else []), *plan.hosts]
        async with self._maker() as db:
            for s in rows:
                await db.execute(
                    insert(Settlement)
                    .values(
                        id=uuid.uuid4(),
                        line_id=plan.line.id,
                        party=s.party,
                        party_ref=s.ref,
                        address=s.address,
                        grams=s.grams,
                        share_cop=s.cop,
                        created_at=self._now(),
                    )
                    .on_conflict_do_update(
                        index_elements=["line_id", "party", "party_ref"],
                        set_={"address": s.address, "grams": s.grams, "share_cop": s.cop},
                    )
                )
            await db.commit()

    async def _mark_deposits(self, line_id: uuid.UUID, shares: list[Share], tx: str | None) -> None:
        for s in shares:
            advance = await self._chain.advance_of(uuid.UUID(s.ref))
            await self._mark(line_id, s, max(s.cop - advance, 0), tx)

    async def _mark(self, line_id: uuid.UUID, s: Share, paid: int, tx: str | None) -> None:
        async with self._maker() as db:
            row = await db.scalar(
                select(Settlement)
                .where(
                    Settlement.line_id == line_id,
                    Settlement.party == s.party,
                    Settlement.party_ref == s.ref,
                )
                .with_for_update()
            )
            if row is not None and row.paid_cop is None:
                row.paid_cop, row.tx_hash = paid, tx
                await db.commit()

    async def _log_tx(self, line_id: uuid.UUID, step: str, tx: str) -> None:
        async with self._maker() as db:
            line = await db.get(SaleLine, line_id, with_for_update=True)
            assert line is not None
            line.txs = [*line.txs, {"step": step, "tx": tx, "at": self._now().isoformat()}]
            line.updated_at = self._now()
            await db.commit()
