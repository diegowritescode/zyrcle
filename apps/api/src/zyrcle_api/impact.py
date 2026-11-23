"""Impact certificates (docs/adr/0027): issuing them, and the worker that anchors their roots.

A certificate counts the credited deposits of a host (or one site) whose bag's sale settled in the
month, and claims their `co2e` attribute in the same transaction, so no gram enters two
certificates. The anchor worker then pins a public copy on IPFS (when Pinata is configured) and
writes the Merkle root, with the copy's CID, on ZyrcleChain.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .chain import Chain
from .config import Settings
from .domain.impact import (
    FACTORS_VERSION,
    Leaf,
    anchor_data,
    certificate_document,
    co2e_g,
    merkle_root,
)
from .domain.session_machine import CREDITED
from .errors import Conflict, Invalid, NotFound
from .ipfs import PinataPin, gateway_url
from .models import (
    Certificate,
    CollectionFill,
    Container,
    DepositSession,
    Host,
    ImpactClaim,
    SaleLine,
    Site,
)

log = logging.getLogger(__name__)
RETRY = timedelta(seconds=30)


def utcnow() -> datetime:
    return datetime.now(UTC)


def month_bounds(period: str, tz: ZoneInfo) -> tuple[datetime, datetime]:
    try:
        year, month = (int(x) for x in period.split("-"))
        start = datetime(year, month, 1, tzinfo=tz)
    except ValueError:
        raise Invalid("the period is a month: YYYY-MM") from None
    end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=tz)
    return start, end


def certificate_view(c: Certificate, host: Host, site: Site | None, gateway: str) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "host": {"id": str(host.id), "name": host.name, "kind": host.kind},
        "site": {"id": str(site.id), "name": site.name} if site else None,
        "period": c.period,
        "factors_version": c.factors_version,
        "deposits": c.deposits,
        "participants": c.participants,
        "grams": c.grams,
        "co2e_g": c.co2e_g,
        "by_material": c.by_material,
        "merkle_root": c.merkle_root,
        "status": c.status,
        "anchor_tx": c.anchor_tx,
        "ipfs_cid": c.ipfs_cid,
        "ipfs_url": gateway_url(gateway, c.ipfs_cid),
        "issued_by": c.issued_by,
        "created_at": c.created_at.isoformat(),
        "anchored_at": c.anchored_at.isoformat() if c.anchored_at else None,
    }


async def certificate_leaves(db: AsyncSession, certificate_id: uuid.UUID) -> list[dict[str, Any]]:
    """The deposits a certificate claimed, in a fixed order: what its Merkle root is built from."""
    rows = await db.execute(
        select(ImpactClaim.session_id, DepositSession.declared_material, ImpactClaim.grams)
        .join(DepositSession, DepositSession.id == ImpactClaim.session_id)
        .where(ImpactClaim.certificate_id == certificate_id)
        .order_by(ImpactClaim.session_id)
    )
    return [
        {"deposit_id": str(sid), "material": material, "grams": grams}
        for sid, material, grams in rows
    ]


class ImpactService:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        settings: Settings,
        clock: Callable[[], datetime] = utcnow,
    ):
        self._maker = maker
        self._tz = ZoneInfo(settings.timezone)
        self._gateway = settings.ipfs_gateway
        self._now = clock

    async def _eligible(
        self, db: AsyncSession, host_id: uuid.UUID, site_id: uuid.UUID | None, period: str
    ) -> list[DepositSession]:
        """Credited deposits of the host (or site) whose bag's sale settled in the month and whose
        `co2e` is not claimed yet."""
        start, end = month_bounds(period, self._tz)
        query = (
            select(DepositSession)
            .join(
                CollectionFill,
                and_(
                    CollectionFill.collection_id == DepositSession.collection_id,
                    CollectionFill.material == DepositSession.declared_material,
                    CollectionFill.bag_id.is_not(None),
                ),
            )
            .join(SaleLine, SaleLine.bag_id == CollectionFill.bag_id)
            .join(Container, Container.id == DepositSession.container_id)
            .join(Site, Site.id == Container.site_id)
            .where(
                Site.host_id == host_id,
                SaleLine.status == "settled",
                SaleLine.settled_at >= start,
                SaleLine.settled_at < end,
                DepositSession.state.in_([s.value for s in CREDITED]),
                DepositSession.deposited_g > 0,
                ~exists().where(
                    ImpactClaim.session_id == DepositSession.id, ImpactClaim.attribute == "co2e"
                ),
            )
            .distinct()
        )
        if site_id is not None:
            query = query.where(Container.site_id == site_id)
        return list(await db.scalars(query))

    @staticmethod
    def _summary(deposits: list[DepositSession]) -> dict[str, Any]:
        by_material: dict[str, dict[str, int]] = {}
        for d in deposits:
            entry = by_material.setdefault(d.declared_material, {"grams": 0, "co2e_g": 0})
            entry["grams"] += d.deposited_g or 0
        for material, entry in by_material.items():
            entry["co2e_g"] = co2e_g(material, entry["grams"])
        leaves = [Leaf(str(d.id), d.declared_material, d.deposited_g or 0) for d in deposits]
        return {
            "deposits": len(deposits),
            "participants": len({d.resident_id for d in deposits}),
            "grams": sum(e["grams"] for e in by_material.values()),
            "co2e_g": sum(e["co2e_g"] for e in by_material.values()),
            "by_material": dict(sorted(by_material.items())),
            "merkle_root": "0x" + merkle_root(leaves).hex(),
        }

    async def _place(
        self, db: AsyncSession, host_id: uuid.UUID, site_id: uuid.UUID | None
    ) -> tuple[Host, Site | None]:
        host = await db.get(Host, host_id)
        if host is None:
            raise NotFound("unknown host")
        site = None
        if site_id is not None:
            site = await db.get(Site, site_id)
            if site is None or site.host_id != host_id:
                raise NotFound("unknown site of this host")
        return host, site

    async def preview(
        self, host_id: uuid.UUID, site_id: uuid.UUID | None, period: str
    ) -> dict[str, Any]:
        async with self._maker() as db:
            await self._place(db, host_id, site_id)
            deposits = await self._eligible(db, host_id, site_id, period)
        return {"period": period, "factors_version": FACTORS_VERSION, **self._summary(deposits)}

    async def issue(
        self, host_id: uuid.UUID, site_id: uuid.UUID | None, period: str, who: str
    ) -> dict[str, Any]:
        now = self._now()
        async with self._maker() as db:
            host, site = await self._place(db, host_id, site_id)
            deposits = await self._eligible(db, host_id, site_id, period)
            if not deposits:
                raise Conflict("no sold material left to certify in that month")
            summary = self._summary(deposits)
            c = Certificate(
                id=uuid.uuid4(),
                host_id=host_id,
                site_id=site_id,
                period=period,
                factors_version=FACTORS_VERSION,
                status="issued",
                next_attempt_at=now,
                issued_by=who,
                created_at=now,
                **summary,
            )
            db.add(c)
            for d in deposits:
                db.add(
                    ImpactClaim(
                        id=uuid.uuid4(),
                        session_id=d.id,
                        attribute="co2e",
                        certificate_id=c.id,
                        grams=d.deposited_g or 0,
                        created_at=now,
                    )
                )
            try:
                await db.commit()
            except IntegrityError:
                # Another certificate claimed some of these deposits at the same moment.
                raise Conflict("some of that material was just certified; preview again") from None
            return certificate_view(c, host, site, self._gateway)

    async def get(self, certificate_id: uuid.UUID, with_leaves: bool = True) -> dict[str, Any]:
        async with self._maker() as db:
            c = await db.get(Certificate, certificate_id)
            if c is None:
                raise NotFound("unknown certificate")
            host = await db.get(Host, c.host_id)
            site = await db.get(Site, c.site_id) if c.site_id else None
            assert host is not None
            view = certificate_view(c, host, site, self._gateway)
            if with_leaves:
                view["leaves"] = await certificate_leaves(db, c.id)
            return view

    async def list(self, host_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        async with self._maker() as db:
            query = (
                select(Certificate, Host, Site)
                .join(Host, Host.id == Certificate.host_id)
                .outerjoin(Site, Site.id == Certificate.site_id)
                .order_by(Certificate.period.desc(), Certificate.created_at.desc())
            )
            if host_id is not None:
                query = query.where(Certificate.host_id == host_id)
            return [certificate_view(c, h, s, self._gateway) for c, h, s in await db.execute(query)]


class AnchorWorker:
    """Anchors each issued certificate from the Treasury operator key. With Pinata configured it
    first pins the certificate's public copy on IPFS and keeps the CID, so a retry after a failed
    anchor reuses it; the anchor then carries the CID too."""

    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        chain: Chain,
        operator,
        pinata: PinataPin | None = None,
        gateway: str = "",
        clock: Callable[[], datetime] = utcnow,
    ):
        self._maker = maker
        self._chain = chain
        self._operator = operator
        self._pinata = pinata
        self._gateway = gateway
        self._now = clock

    async def run_once(self, batch: int = 5) -> int:
        now = self._now()
        async with self._maker() as db:
            rows = list(
                await db.scalars(
                    select(Certificate)
                    .where(
                        Certificate.status == "issued",
                        or_(
                            Certificate.next_attempt_at.is_(None),
                            Certificate.next_attempt_at <= now,
                        ),
                    )
                    .order_by(Certificate.created_at)
                    .limit(batch)
                    .with_for_update(skip_locked=True)
                )
            )
            # Claimed for a while, so a slow chain does not hold locks or get a second send.
            for c in rows:
                c.attempts, c.next_attempt_at = c.attempts + 1, now + timedelta(minutes=5)
            await db.commit()
            work = [(c.id, c.merkle_root, c.ipfs_cid) for c in rows]
        for cid, root, ipfs_cid in work:
            await self._anchor(cid, root, ipfs_cid)
        return len(work)

    async def _pin(self, certificate_id: uuid.UUID) -> str:
        """Pin the public copy and keep its CID before anything is written on chain."""
        assert self._pinata is not None
        async with self._maker() as db:
            c = await db.get(Certificate, certificate_id)
            assert c is not None
            host = await db.get(Host, c.host_id)
            site = await db.get(Site, c.site_id) if c.site_id else None
            assert host is not None
            document = certificate_document(
                certificate_view(c, host, site, self._gateway),
                await certificate_leaves(db, c.id),
            )
        cid = await self._pinata.pin_json(
            document,
            name=f"zyrcle-certificate-{certificate_id}",
            keyvalues={"host": str(document["host"]["id"]), "period": document["period"]},
        )
        async with self._maker() as db:
            c = await db.get(Certificate, certificate_id, with_for_update=True)
            assert c is not None
            c.ipfs_cid = cid
            await db.commit()
        return cid

    async def _anchor(self, cid: uuid.UUID, root: str, ipfs_cid: str | None) -> None:
        tx, error = None, None
        try:
            if self._pinata is not None and ipfs_cid is None:
                ipfs_cid = await self._pin(cid)
            tx = await self._chain.anchor(
                self._operator,
                anchor_data(cid.bytes, bytes.fromhex(root.removeprefix("0x")), ipfs_cid),
            )
        except Exception as e:  # Pinata or the chain is down, or the key has no gas: retry
            error = f"{type(e).__name__}: {e}"
        async with self._maker() as db:
            c = await db.get(Certificate, cid, with_for_update=True)
            assert c is not None
            if tx:
                c.status, c.anchor_tx, c.anchored_at, c.last_error = (
                    "anchored",
                    tx,
                    self._now(),
                    None,
                )
            else:
                c.last_error, c.next_attempt_at = error, self._now() + RETRY
            await db.commit()
        log.info("certificate %s: %s", cid, tx or error)
