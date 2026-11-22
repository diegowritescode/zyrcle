"""Push notifications to the resident app through Expo's push service
(docs/adr/0008-push-notifications.md).

Whatever causes a notification (a payout confirmed on chain, a deposit sent to review) writes it to
the `notification` outbox in the same transaction, so a crash can neither lose it nor send it for
something that was rolled back. `NotificationWorker` delivers the outbox: one HTTP request per batch
of up to 100 messages, then, about 15 minutes later, Expo's receipts say whether Apple or Google
accepted each one. Tokens of uninstalled apps (DeviceNotRegistered) are disabled on either answer.
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import Container, DepositSession, Notification, Payout, PushToken

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 6
BATCH = 100  # Expo's limit of messages per request
RECEIPTS_BATCH = 1000  # Expo's limit of receipt ids per request
RECEIPTS_KEPT = timedelta(hours=24)  # Expo deletes receipts after a day
# Android notification channel of each kind (created by the app, apps/mobile/src/lib/notifications).
CHANNEL = {
    "payout_confirmed": "payments",
    "deposit_approved": "payments",
    "deposit_review": "deposits",
    "deposit_rejected": "deposits",
    "recovery_started": "account",
    "recovery_done": "account",
    "recovery_cancelled": "account",
}
MATERIAL_NAMES = {
    "pet": "PET",
    "hdpe": "HDPE",
    "metal": "latas",
    "glass": "vidrio",
    "paper": "papel",
    "cardboard": "cartón",
}


def pesos(amount: int) -> str:
    return "$" + f"{amount:,}".replace(",", ".")


def weight(grams: int | None) -> str:
    g = grams or 0
    return f"{g} g" if g < 1000 else f"{g / 1000:.2f}".replace(".", ",") + " kg"


def _what(session: DepositSession, container_name: str) -> str:
    material = MATERIAL_NAMES.get(session.declared_material, session.declared_material)
    return f"{weight(session.deposited_g)} de {material} en {container_name}"


async def enqueue(
    db: AsyncSession,
    *,
    resident_id: uuid.UUID,
    kind: str,
    dedupe_key: str,
    title: str,
    body: str,
    data: dict[str, Any],
    now: datetime,
) -> None:
    """Add a notification to the outbox, once per `dedupe_key`, in the caller's transaction."""
    await db.execute(
        insert(Notification)
        .values(
            id=uuid.uuid4(),
            resident_id=resident_id,
            kind=kind,
            dedupe_key=dedupe_key,
            title=title,
            body=body,
            data=data,
            status="pending",
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )


async def notify_session(db: AsyncSession, session: DepositSession, kind: str, now: datetime):
    """Deposit outcomes the resident may not be watching: review, and its verdict."""
    container = await db.get(Container, session.container_id)
    what = _what(session, container.name if container else session.container_id)
    if kind == "deposit_review":
        title = "Tu depósito quedó en revisión"
        body = f"Algo no cuadró entre el peso y el volumen ({what}). Una persona lo revisa."
    elif kind == "deposit_rejected":
        title = "Tu depósito no fue aprobado"
        body = f"{what[0].upper()}{what[1:]}." + (
            f" Motivo: {session.review_note}" if session.review_note else ""
        )
    elif kind == "deposit_approved":
        title = "Aprobamos tu depósito"
        body = f"{what[0].upper()}{what[1:]} quedó acreditado."
    else:
        raise ValueError(kind)
    await enqueue(
        db,
        resident_id=session.resident_id,
        kind=kind,
        dedupe_key=f"{kind}:{session.id}",
        title=title,
        body=body,
        data={"url": "/history", "session_id": str(session.id)},
        now=now,
    )


async def notify_payout(db: AsyncSession, payout: Payout, now: datetime) -> None:
    session = await db.get(DepositSession, payout.session_id)
    if session is None:
        return
    container = await db.get(Container, session.container_id)
    what = _what(session, container.name if container else session.container_id)
    approved = session.state == "approved"
    await enqueue(
        db,
        resident_id=session.resident_id,
        kind="payout_confirmed",
        dedupe_key=f"payout_confirmed:{payout.id}",
        title=(
            f"Aprobamos tu depósito: te pagamos {pesos(payout.amount_cop)}"
            if approved
            else f"Te pagamos {pesos(payout.amount_cop)}"
        ),
        body=f"Por {what}. Ya está en tu saldo.",
        data={"url": "/history", "session_id": str(session.id), "tx_hash": payout.tx_hash},
        now=now,
    )


# ---------------------------------------------------------------------------------- delivery


class PushUnavailable(Exception):
    """Expo could not take the request now (network, 429, 5xx): try again later."""


class ExpoPush:
    """Client for https://docs.expo.dev/push-notifications/sending-notifications/."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, access_token: str | None = None):
        self._http = http
        self._base = base_url.rstrip("/")
        self._headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if access_token:
            self._headers["Authorization"] = f"Bearer {access_token}"

    async def _post(self, path: str, payload: Any) -> Any:
        try:
            r = await self._http.post(f"{self._base}{path}", json=payload, headers=self._headers)
        except httpx.HTTPError as e:
            raise PushUnavailable(f"{type(e).__name__}: {e}") from e
        if r.status_code == 429 or r.status_code >= 500:
            raise PushUnavailable(f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        if r.status_code >= 400 or "data" not in body:
            # A request-level error (bad credentials, malformed request): retrying will not help.
            raise ValueError(f"HTTP {r.status_code}: {body.get('errors', body)}")
        return body["data"]

    async def send(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One ticket per message, in order: {"status": "ok", "id"} or {"status": "error", ...}."""
        return await self._post("/send", messages)

    async def receipts(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        """Receipts by ticket id. Ids whose receipt is not ready yet are missing."""
        return await self._post("/getReceipts", {"ids": ids})


def _error_of(result: dict[str, Any]) -> str:
    return (result.get("details") or {}).get("error") or result.get("message") or "unknown"


class NotificationWorker:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        push: ExpoPush,
        receipt_delay: timedelta,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._maker = maker
        self._push = push
        self._receipt_delay = receipt_delay
        self._now = clock

    async def run_once(self) -> int:
        sent = await self._send_due()
        await self._check_receipts()
        return sent

    async def _send_due(self, batch: int = 50) -> int:
        """Send due notifications. Rows stay locked (SKIP LOCKED) while their request is in flight,
        so replicas never send the same one; a crash rolls back and they are sent again."""
        now = self._now()
        async with self._maker() as db:
            due = list(
                await db.scalars(
                    select(Notification)
                    .where(
                        Notification.status == "pending",
                        or_(
                            Notification.next_attempt_at.is_(None),
                            Notification.next_attempt_at <= now,
                        ),
                    )
                    .order_by(Notification.created_at)
                    .limit(batch)
                    .with_for_update(skip_locked=True)
                )
            )
            if not due:
                return 0
            tokens: dict[uuid.UUID, list[PushToken]] = defaultdict(list)
            for t in await db.scalars(
                select(PushToken)
                .where(
                    PushToken.resident_id.in_({n.resident_id for n in due}),
                    PushToken.disabled_at.is_(None),
                )
                .with_for_update()
            ):
                tokens[t.resident_id].append(t)

            chunk: list[Notification] = []
            size = 0
            for n in due:
                mine = tokens.get(n.resident_id, [])
                if not mine:
                    n.status = "skipped"  # no app registered: nothing to deliver to
                    continue
                if chunk and size + len(mine) > BATCH:
                    await self._deliver(chunk, tokens, now)
                    chunk, size = [], 0
                chunk.append(n)
                size += len(mine)
            if chunk:
                await self._deliver(chunk, tokens, now)
            await db.commit()
            return len(due)

    async def _deliver(
        self, chunk: list[Notification], tokens: dict[uuid.UUID, list[PushToken]], now: datetime
    ) -> None:
        messages: list[dict[str, Any]] = []
        owners: list[tuple[Notification, PushToken]] = []
        for n in chunk:
            for t in tokens[n.resident_id]:
                messages.append(
                    {
                        "to": t.token,
                        "title": n.title,
                        "body": n.body,
                        "data": {**n.data, "kind": n.kind},
                        "sound": "default",
                        "priority": "high",
                        "channelId": CHANNEL.get(n.kind, "default"),
                    }
                )
                owners.append((n, t))
        for n in chunk:
            n.attempts += 1
        try:
            tickets = await self._push.send(messages)
            if len(tickets) != len(messages):
                raise ValueError(f"{len(tickets)} tickets for {len(messages)} messages")
        except PushUnavailable as e:
            for n in chunk:
                self._retry_or_fail(n, str(e), now)
            log.warning("push send failed, will retry: %s", e)
            return
        except ValueError as e:
            for n in chunk:
                n.status, n.last_error = "failed", str(e)
            log.error("push send rejected: %s", e)
            return

        ok: dict[uuid.UUID, list[dict[str, str]]] = defaultdict(list)
        errors: dict[uuid.UUID, list[str]] = defaultdict(list)
        for (n, t), ticket in zip(owners, tickets, strict=True):
            if ticket.get("status") == "ok":
                ok[n.id].append({"token": t.token, "id": ticket["id"]})
                continue
            error = _error_of(ticket)
            errors[n.id].append(error)
            if error == "DeviceNotRegistered":
                t.disabled_at = now
        for n in chunk:
            if ok[n.id]:
                n.status, n.sent_at, n.tickets = "sent", now, ok[n.id]
                n.last_error = "; ".join(errors[n.id]) or None
            elif "MessageRateExceeded" in errors[n.id]:
                self._retry_or_fail(n, "MessageRateExceeded", now)
            else:
                n.status, n.last_error = "failed", "; ".join(errors[n.id])

    @staticmethod
    def _retry_or_fail(n: Notification, error: str, now: datetime) -> None:
        n.last_error = error
        if n.attempts >= MAX_ATTEMPTS:
            n.status = "failed"
        else:
            n.next_attempt_at = now + timedelta(seconds=min(15 * 2**n.attempts, 1800))

    async def _check_receipts(self) -> None:
        now = self._now()
        async with self._maker() as db:
            rows = list(
                await db.scalars(
                    select(Notification)
                    .where(
                        Notification.status == "sent",
                        Notification.receipts_checked_at.is_(None),
                        Notification.sent_at <= now - self._receipt_delay,
                    )
                    .order_by(Notification.sent_at)
                    .limit(RECEIPTS_BATCH)
                    .with_for_update(skip_locked=True)
                )
            )
            ids = [t["id"] for n in rows for t in n.tickets or []][:RECEIPTS_BATCH]
            if not ids:
                return
            try:
                receipts = await self._push.receipts(ids)
            except (PushUnavailable, ValueError) as e:
                log.warning("push receipts unavailable: %s", e)
                return
            gone: set[str] = set()
            for n in rows:
                pending = False
                problems = []
                for t in n.tickets or []:
                    receipt = receipts.get(t["id"])
                    if receipt is None:
                        pending = True
                    elif receipt.get("status") != "ok":
                        error = _error_of(receipt)
                        problems.append(error)
                        if error == "DeviceNotRegistered":
                            gone.add(t["token"])
                if problems:
                    n.last_error = "; ".join(problems)
                    log.warning("push %s not delivered: %s", n.id, n.last_error)
                if not pending or n.sent_at <= now - RECEIPTS_KEPT:
                    n.receipts_checked_at = now
            if gone:
                for t in await db.scalars(select(PushToken).where(PushToken.token.in_(gone))):
                    t.disabled_at = now
            await db.commit()
