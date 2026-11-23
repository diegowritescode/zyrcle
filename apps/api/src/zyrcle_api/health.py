"""Is everything working? For the console and for admins' email alerts (docs/adr/0028).

Every outbox should drain, the chain should keep producing blocks while there is work for it, the
validator node should report itself healthy, the Treasury should have pesos left to mint against,
and the keys that pay gas should have some. Each check that fails becomes a warning in Spanish, the
language of the people who act on it.

ZyrcleChain (Subnet-EVM) makes a block only when there is a transaction, so an old last block on
its own means a quiet chain, not a stalled one. It is a warning only when work has been waiting for
the chain that long too (amendment of ADR 0028, 2026-11-23).
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .chain import WEI_PER_COP, Chain
from .config import Settings
from .mail import enqueue_email, render_html
from .models import (
    AccountRecovery,
    Certificate,
    Device,
    EmailMessage,
    Notification,
    Operator,
    PaymentRequest,
    Payout,
    RedemptionRequest,
    SaleLine,
)

log = logging.getLogger(__name__)

# (label, model, statuses that should drain, statuses that need a person)
OUTBOXES = [
    ("anticipos", Payout, ("pending", "submitting", "deferred"), ("failed",)),
    ("avisos push", Notification, ("pending",), ("failed",)),
    ("correos", EmailMessage, ("pending",), ("failed",)),
    ("liquidaciones", SaleLine, ("pending", "settling", "waiting"), ("failed",)),
    ("certificados", Certificate, ("issued",), ("failed",)),
    ("recuperaciones", AccountRecovery, ("starting", "cancelling"), ("failed",)),
]


# Rows that wait on a transaction: (model, statuses). Their age counts from `updated_at` when the
# model has it (a sale line is created long before it settles), else from `created_at`.
CHAIN_WORK = [
    (Payout, ("pending", "submitting")),
    (SaleLine, ("settling",)),
    (Certificate, ("issued",)),
    (AccountRecovery, ("starting", "cancelling")),
    (PaymentRequest, ("paying",)),
    (RedemptionRequest, ("requested",)),
]


def chain_stalled(block_age_s: int, waiting_s: int | None, threshold_s: int) -> bool:
    """A stall is an old last block while something has waited for the chain as long."""
    return block_age_s > threshold_s and waiting_s is not None and waiting_s > threshold_s


async def _oldest_chain_work(db: AsyncSession) -> datetime | None:
    oldest = None
    for model, statuses in CHAIN_WORK:
        since = getattr(model, "updated_at", model.created_at)
        first = await db.scalar(select(func.min(since)).where(model.status.in_(statuses)))
        if first is not None and (oldest is None or first < oldest):
            oldest = first
    return oldest


async def _node_healthy(url: str, http: httpx.AsyncClient | None) -> bool:
    """The node's own health endpoint (`/ext/health` on AvalancheGo)."""
    try:
        if http is None:
            async with httpx.AsyncClient(timeout=5) as own:
                r = await own.get(url)
        else:
            r = await http.get(url, timeout=5)
        return r.status_code == 200 and r.json().get("healthy") is True
    except (httpx.HTTPError, ValueError):
        return False


def utcnow() -> datetime:
    return datetime.now(UTC)


async def _outboxes(db: AsyncSession, now: datetime, stuck_after: timedelta) -> list[dict]:
    out = []
    for label, model, draining, failed in OUTBOXES:
        pending, oldest = (
            await db.execute(
                select(func.count(), func.min(model.created_at)).where(model.status.in_(draining))
            )
        ).one()
        failures = await db.scalar(
            select(func.count()).select_from(model).where(model.status.in_(failed))
        )
        out.append(
            {
                "name": label,
                "pending": pending,
                "failed": failures or 0,
                "oldest_pending_min": None
                if oldest is None
                else int((now - oldest).total_seconds() // 60),
                "stuck": oldest is not None and now - oldest > stuck_after,
            }
        )
    return out


async def report(
    maker: async_sessionmaker[AsyncSession],
    settings: Settings,
    chain: Chain | None,
    keys: dict[str, str],
    mqtt_connected: bool,
    clock: Callable[[], datetime] = utcnow,
    http: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """The whole picture. `keys` maps a role name to the address that pays its gas."""
    now = clock()
    warnings: list[dict[str, str]] = []
    async with maker() as db:
        outboxes = await _outboxes(db, now, timedelta(minutes=settings.alert_stuck_after_min))
        online = await db.scalar(
            select(func.count())
            .select_from(Device)
            .where(Device.last_seen_at > now - timedelta(seconds=settings.device_offline_after_s))
        )
        devices = await db.scalar(select(func.count()).select_from(Device))
        waiting_since = await _oldest_chain_work(db)
    for box in outboxes:
        if box["stuck"]:
            warnings.append(
                {
                    "kind": f"stuck:{box['name']}",
                    "text": f"La cola de {box['name']} no avanza: lo más viejo lleva "
                    f"{box['oldest_pending_min']} minutos esperando.",
                }
            )
        if box["failed"]:
            warnings.append(
                {
                    "kind": f"failed:{box['name']}",
                    "text": f"Hay {box['failed']} {box['name']} con error que necesitan revisión.",
                }
            )
    if not mqtt_connected:
        warnings.append({"kind": "mqtt", "text": "El servidor no está conectado al broker MQTT."})

    chain_view: dict[str, Any] | None = None
    if chain is not None:
        chain_view = {"keys": {}}
        try:
            block = await chain.w3.eth.get_block("latest")
            age = int(now.timestamp()) - int(block["timestamp"])
            waiting = None if waiting_since is None else int((now - waiting_since).total_seconds())
            chain_view.update(block=int(block["number"]), block_age_s=age, waiting_s=waiting)
            if chain_stalled(age, waiting, settings.alert_chain_stale_min * 60):
                assert waiting is not None
                warnings.append(
                    {
                        "kind": "chain_stale",
                        "text": f"Hay operaciones esperando a ZyrcleChain hace {waiting // 60} "
                        f"minutos y no produce bloques hace {age // 60}: revisa el validador y su "
                        "saldo en la P-Chain.",
                    }
                )
            if chain.treasury is not None:
                state = await chain.state()
                chain_view["available_cop"] = state.available_cop
                if state.available_cop < settings.alert_available_min_cop:
                    warnings.append(
                        {
                            "kind": "treasury_low",
                            "text": f"A la tesorería le quedan {state.available_cop:,} pesos para "
                            "pagar: registra ventas o capital.",
                        }
                    )
            for role, address in keys.items():
                zyr = await chain.balance_wei(address) / WEI_PER_COP
                chain_view["keys"][role] = {"address": address, "zyr": round(zyr, 4)}
                if zyr < settings.alert_gas_min_zyr:
                    warnings.append(
                        {
                            "kind": f"gas:{role}",
                            "text": f"La llave {role} tiene {zyr:.2f} ZYR para gas: recárgala "
                            "desde la llave de administrador.",
                        }
                    )
        except Exception as e:  # the chain being unreachable is itself the warning
            chain_view["error"] = f"{type(e).__name__}: {e}"
            warnings.append({"kind": "chain_down", "text": "No logramos leer ZyrcleChain."})
        if settings.chain_health_url:
            healthy = await _node_healthy(settings.chain_health_url, http)
            chain_view["node_healthy"] = healthy
            if not healthy:
                warnings.append(
                    {
                        "kind": "node_unhealthy",
                        "text": "El nodo validador de ZyrcleChain dice que no está sano: revisa "
                        "el contenedor del nodo y su saldo en la P-Chain.",
                    }
                )
    return {
        "checked_at": now.isoformat(),
        "ok": not warnings,
        "warnings": warnings,
        "outboxes": outboxes,
        "devices": {"online": online or 0, "total": devices or 0},
        "mqtt": mqtt_connected,
        "chain": chain_view,
    }


class AlertWorker:
    """Emails every active admin each warning, at most once a day per kind."""

    def __init__(self, maker, settings: Settings, snapshot, clock: Callable[[], datetime] = utcnow):
        self._maker = maker
        self._s = settings
        self._snapshot = snapshot  # async () -> report
        self._now = clock

    async def run_once(self) -> int:
        current = await self._snapshot()
        if current["ok"]:
            return 0
        today = self._now().date().isoformat()
        async with self._maker() as db:
            admins = list(
                await db.scalars(
                    select(Operator.email).where(Operator.role == "admin", Operator.active)
                )
            )
            for w in current["warnings"]:
                for email in admins:
                    title = "Zyrcle necesita atención"
                    await enqueue_email(
                        db,
                        to=email,
                        kind="alert",
                        dedupe_key=f"alert:{w['kind']}:{today}:{email}"[:120],
                        subject=title,
                        text=f"{w['text']}\n\nMás detalle en la consola, pestaña Resumen.",
                        html_body=render_html(title, [w["text"], "Más detalle en la consola."]),
                        now=self._now(),
                    )
            await db.commit()
        return len(current["warnings"])
