"""Email through Resend (docs/adr/0010-smart-accounts-and-recovery.md).

Emails are written to an outbox (`email_message`) in the transaction that causes them and sent by
`EmailWorker`, the same way push notifications are (notifications.py). Resend's HTTP API is used
rather than its SMTP relay: it runs over HTTPS (many VPS providers block outgoing SMTP ports),
reports errors by name, and honours an `Idempotency-Key`, so a retry after a timeout never sends
the same email twice.
"""

import html
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import EmailMessage

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 6
# Kinds whose body holds a one-time code: cleared once sent, and pointless to send once expired.
CODE_KINDS = {"code_verify", "code_recover"}
CODE_TTL = timedelta(minutes=10)


class MailUnavailable(Exception):
    """Try again later. `retry_at` is set when the provider says when (quota resets)."""

    def __init__(self, detail: str, retry_at: datetime | None = None):
        super().__init__(detail)
        self.retry_at = retry_at


class MailRejected(Exception):
    """The provider refused this email for good (invalid address, unverified domain, bad key)."""


class ResendMail:
    def __init__(self, http: httpx.AsyncClient, base_url: str, api_key: str, sender: str):
        self._http = http
        self._url = base_url.rstrip("/") + "/emails"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            # Resend rejects requests without a User-Agent (403).
            "User-Agent": "zyrcle-api/0.1",
        }
        self._sender = sender

    async def send(
        self, *, to: str, subject: str, text: str, html_body: str, idempotency_key: str
    ) -> str:
        try:
            r = await self._http.post(
                self._url,
                headers={**self._headers, "Idempotency-Key": idempotency_key},
                json={
                    "from": self._sender,
                    "to": [to],
                    "subject": subject,
                    "text": text,
                    "html": html_body,
                },
            )
        except httpx.HTTPError as e:
            raise MailUnavailable(f"{type(e).__name__}: {e}") from None
        if r.status_code == 200:
            return r.json()["id"]
        name, message = _error(r)
        if r.status_code == 429:
            if name in ("daily_quota_exceeded", "monthly_quota_exceeded"):
                raise MailUnavailable(f"{name}: {message}", retry_at=_next_utc_midnight())
            raise MailUnavailable(f"{name}: {message}")
        if r.status_code >= 500 or name == "concurrent_idempotent_requests":
            raise MailUnavailable(f"{r.status_code} {name}: {message}")
        raise MailRejected(f"{r.status_code} {name}: {message}")


class LogMail:
    """Local development: log emails instead of sending them (settings.email_log_only)."""

    async def send(
        self, *, to: str, subject: str, text: str, html_body: str, idempotency_key: str
    ) -> str:
        log.warning("email to %s: %s\n%s", to, subject, text)
        return f"log-{idempotency_key}"


def _error(r: httpx.Response) -> tuple[str, str]:
    try:
        body = r.json()
        return str(body.get("name", "unknown")), str(body.get("message", ""))
    except ValueError:
        return "unknown", r.text[:200]


def _next_utc_midnight() -> datetime:
    now = datetime.now(UTC)
    return (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)


async def enqueue_email(
    db: AsyncSession,
    *,
    to: str,
    kind: str,
    dedupe_key: str,
    subject: str,
    text: str,
    html_body: str,
    now: datetime,
) -> None:
    """Add an email to the outbox, once per `dedupe_key`. Commits with the caller's transaction."""
    await db.execute(
        insert(EmailMessage)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            dedupe_key=dedupe_key,
            to=to,
            subject=subject,
            text_body=text,
            html_body=html_body,
            status="pending",
            next_attempt_at=now,
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )


def render_html(title: str, paragraphs: list[str], code: str | None = None) -> str:
    """A plain, mobile-friendly email body. Text is escaped; `code` is shown large."""
    parts = [
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.5">{html.escape(p)}</p>'
        for p in paragraphs
    ]
    if code:
        parts.insert(
            1,
            '<p style="margin:8px 0 24px;font-size:32px;font-weight:700;letter-spacing:6px;'
            f'font-family:ui-monospace,Menlo,monospace;color:#064E3B">{html.escape(code)}</p>',
        )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:480px;margin:0 auto;padding:24px;color:#0F172A">'
        '<p style="margin:0 0 24px;font-size:20px;font-weight:700;color:#10B981">Zyrcle</p>'
        f'<h1 style="margin:0 0 16px;font-size:20px">{html.escape(title)}</h1>'
        + "".join(parts)
        + '<p style="margin:24px 0 0;font-size:13px;color:#64748B">Zyrcle nunca te va a pedir '
        "este código ni tu contraseña por teléfono, chat o correo.</p></div>"
    )


class EmailWorker:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        mail: ResendMail | LogMail,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._maker = maker
        self._mail = mail
        self._now = clock

    async def run_once(self, batch: int = 10) -> int:
        now = self._now()
        async with self._maker() as db:
            rows = list(
                await db.scalars(
                    select(EmailMessage)
                    .where(
                        EmailMessage.status == "pending",
                        or_(
                            EmailMessage.next_attempt_at.is_(None),
                            EmailMessage.next_attempt_at <= now,
                        ),
                    )
                    .order_by(EmailMessage.created_at)
                    .limit(batch)
                    .with_for_update(skip_locked=True)
                )
            )
            for m in rows:
                await self._deliver(m, now)
            await db.commit()
        return len(rows)

    async def _deliver(self, m: EmailMessage, now: datetime) -> None:
        if m.kind in CODE_KINDS and m.created_at < now - CODE_TTL:
            self._finish(m, "failed", "expired before it could be sent")
            return
        m.attempts += 1
        try:
            m.provider_id = await self._mail.send(
                to=m.to,
                subject=m.subject,
                text=m.text_body,
                html_body=m.html_body,
                idempotency_key=str(m.id),
            )
        except MailUnavailable as e:
            if m.attempts >= MAX_ATTEMPTS:
                self._finish(m, "failed", str(e))
            else:
                m.last_error = str(e)
                m.next_attempt_at = e.retry_at or now + timedelta(
                    seconds=min(15 * 2**m.attempts, 1800)
                )
            log.warning("email %s (%s) not sent yet: %s", m.id, m.kind, e)
            return
        except MailRejected as e:
            self._finish(m, "failed", str(e))
            log.error("email %s (%s) rejected: %s", m.id, m.kind, e)
            return
        m.sent_at = now
        self._finish(m, "sent", None)

    @staticmethod
    def _finish(m: EmailMessage, status: str, error: str | None) -> None:
        m.status, m.last_error, m.next_attempt_at = status, error, None
        if m.kind in CODE_KINDS:
            m.subject, m.text_body, m.html_body = "Código de Zyrcle", "", ""
