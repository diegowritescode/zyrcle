"""Recovery email and lost-phone recovery (docs/adr/0010-smart-accounts-and-recovery.md).

A resident's ZYR lives in their smart account; their phone holds the key that controls it. To get
the account back on a new phone:

1. While they still have their phone, the resident confirms an email address (a six-digit code).
2. On the new phone the app signs in with a new key, as a new, empty resident. The resident types
   their email, gets a code there, and types it back.
3. The guardian key asks the account, on chain, to change owner to the new key. The current owner
   is told by push and by email and has 48 hours to cancel. The new phone cannot deposit or book
   in the meantime: whatever it earned would land in the wrong account.
4. After 48 hours the account obeys the new key. The new phone's empty resident is folded into
   the account: same id, history, balance and turns; the old phone loses its notifications and
   its session.
"""

import hashlib
import hmac
import logging
import re
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .chain import Chain, TxFailed, account_address
from .config import Settings
from .errors import (
    CodeInvalid,
    Conflict,
    EmailTaken,
    InvalidEmail,
    NotFound,
    PhoneInUse,
    RecoveryInProgress,
    TooManyCodes,
    TooSoon,
)
from .mail import CODE_TTL, enqueue_email, render_html
from .models import (
    RECOVERY_LIVE,
    AccountRecovery,
    Booking,
    DepositSession,
    EmailCode,
    Notification,
    PushToken,
    Resident,
)
from .notifications import enqueue

log = logging.getLogger(__name__)

RESEND_AFTER = timedelta(seconds=60)
CODES_PER_DAY = 5  # per email address and purpose
CODES_PER_REQUESTER = 10  # per resident and day, whatever the addresses
MAX_CODE_ATTEMPTS = 5
# ZyrcleAccount.RECOVERY_DELAY. Only an estimate here: the chain's readyAt is what counts.
RECOVERY_DELAY = timedelta(hours=48)
LEASE = timedelta(minutes=2)  # how long a claimed recovery is left alone by other workers
DAY = timedelta(days=1)

_EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")
_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


# ---------------------------------------------------------------- helpers


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise InvalidEmail("that does not look like an email address")
    return email


def mask_email(email: str) -> str:
    """d•••@gmail.com: enough for the resident to recognise it, not enough to harvest it."""
    local, _, domain = email.partition("@")
    return f"{local[0]}•••@{domain}"


def when_label(at: datetime, tz: ZoneInfo) -> str:
    """'sábado 28 de noviembre, 3:15 p. m.' (built by hand: Intl differs between runtimes)."""
    t = at.astimezone(tz)
    hour = t.hour % 12 or 12
    suffix = "m." if t.hour == 12 and t.minute == 0 else ("a. m." if t.hour < 12 else "p. m.")
    day = f"{_WEEKDAYS[t.weekday()]} {t.day} de {_MONTHS[t.month - 1]}"
    return f"{day}, {hour}:{t.minute:02d} {suffix}"


def _hash(settings: Settings, purpose: str, email: str, requester: uuid.UUID, code: str) -> str:
    message = f"{purpose}|{email}|{requester}|{code}".encode()
    return hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()


def ensure_account(resident: Resident, settings: Settings) -> None:
    """Give a resident from before smart accounts (address == owner) their account address."""
    factory = settings.account_factory_address
    if settings.accounts_enabled and factory and resident.address == resident.owner_address:
        resident.address = account_address(factory, resident.owner_address)


# ---------------------------------------------------------------- one-time codes


def _code_email(purpose: str, code: str) -> tuple[str, str, str]:
    minutes = int(CODE_TTL.total_seconds() // 60)
    if purpose == "verify":
        subject = f"{code} es tu código de Zyrcle"
        title = "Confirma tu correo"
        lines = [
            "Escribe este código en la app de Zyrcle para confirmar tu correo:",
            f"Vence en {minutes} minutos. Si no fuiste tú, ignora este correo.",
        ]
    else:
        subject = f"{code} es tu código para recuperar tu cuenta de Zyrcle"
        title = "Recupera tu cuenta"
        lines = [
            "Pidieron recuperar tu cuenta de Zyrcle en un teléfono nuevo. Si fuiste tú, escribe "
            "este código en la app:",
            f"Vence en {minutes} minutos. Si no fuiste tú, no se lo des a nadie: con él, otra "
            "persona podría quedarse con tu cuenta.",
        ]
    text = f"{lines[0]}\n\n{code}\n\n{lines[1]}\n"
    return subject, text, render_html(title, lines, code)


async def issue_code(
    db: AsyncSession,
    settings: Settings,
    *,
    purpose: str,
    email: str,
    requester: uuid.UUID,
    now: datetime,
    deliver: bool,
) -> None:
    """Create a code and, if `deliver`, email it. The limits apply either way, so a request for an
    address that has no account looks and behaves exactly like one that has."""
    recent = list(
        await db.scalars(
            select(EmailCode.created_at)
            .where(
                EmailCode.email == email,
                EmailCode.purpose == purpose,
                EmailCode.created_at > now - DAY,
            )
            .order_by(EmailCode.created_at.desc())
        )
    )
    if recent and recent[0] > now - RESEND_AFTER:
        wait = int((recent[0] + RESEND_AFTER - now).total_seconds()) + 1
        raise TooSoon(f"wait {wait} seconds before asking for another code")
    by_requester = await db.scalar(
        select(func.count())
        .select_from(EmailCode)
        .where(EmailCode.resident_id == requester, EmailCode.created_at > now - DAY)
    )
    if len(recent) >= CODES_PER_DAY or (by_requester or 0) >= CODES_PER_REQUESTER:
        raise TooManyCodes("too many codes today, try again tomorrow")

    # A new code replaces the previous ones.
    await db.execute(
        update(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.resident_id == requester,
            EmailCode.used_at.is_(None),
        )
        .values(used_at=now)
    )
    code = f"{secrets.randbelow(10**6):06d}"
    row = EmailCode(
        id=uuid.uuid4(),
        purpose=purpose,
        email=email,
        resident_id=requester,
        code_hash=_hash(settings, purpose, email, requester, code),
        expires_at=now + CODE_TTL,
        created_at=now,
    )
    db.add(row)
    if deliver:
        subject, text, html_body = _code_email(purpose, code)
        await enqueue_email(
            db,
            to=email,
            kind=f"code_{purpose}",
            dedupe_key=f"code:{row.id}",
            subject=subject,
            text=text,
            html_body=html_body,
            now=now,
        )


async def check_code(
    db: AsyncSession,
    settings: Settings,
    *,
    purpose: str,
    email: str,
    requester: uuid.UUID,
    code: str,
    now: datetime,
) -> None:
    """Consume the latest code, or raise CodeInvalid. Wrong guesses are committed even though the
    caller's transaction then fails, and the fifth one burns the code."""
    row = await db.scalar(
        select(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.resident_id == requester,
            EmailCode.used_at.is_(None),
            EmailCode.expires_at > now,
        )
        .order_by(EmailCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if row is None:
        raise CodeInvalid("the code expired or was never requested")
    expected = _hash(settings, purpose, email, requester, code.strip())
    if not hmac.compare_digest(row.code_hash, expected):
        row.attempts += 1
        left = MAX_CODE_ATTEMPTS - row.attempts
        if left <= 0:
            row.used_at = now
        await db.commit()
        raise CodeInvalid(f"wrong code, {max(left, 0)} attempts left")
    row.used_at = now


# ---------------------------------------------------------------- recovery email


async def request_email_code(
    db: AsyncSession, settings: Settings, resident_id: uuid.UUID, raw_email: str, now: datetime
) -> dict[str, Any]:
    email = normalize_email(raw_email)
    await issue_code(
        db, settings, purpose="verify", email=email, requester=resident_id, now=now, deliver=True
    )
    await db.commit()
    return _sent(email)


async def verify_email(
    db: AsyncSession,
    settings: Settings,
    resident_id: uuid.UUID,
    raw_email: str,
    code: str,
    now: datetime,
) -> dict[str, Any]:
    email = normalize_email(raw_email)
    await check_code(
        db, settings, purpose="verify", email=email, requester=resident_id, code=code, now=now
    )
    taken = await db.scalar(
        select(exists().where(Resident.email == email, Resident.id != resident_id))
    )
    if taken:
        raise EmailTaken("another account already uses that email")
    resident = await db.get(Resident, resident_id, with_for_update=True)
    if resident is None:
        raise NotFound("unknown resident")
    resident.email, resident.email_verified_at = email, now
    try:
        await db.commit()
    except IntegrityError:
        raise EmailTaken("another account already uses that email") from None
    return {"email": email, "email_verified_at": now.isoformat()}


def _sent(email: str) -> dict[str, Any]:
    return {
        "sent_to": mask_email(email),
        "expires_in_s": int(CODE_TTL.total_seconds()),
        "resend_in_s": int(RESEND_AFTER.total_seconds()),
    }


# ---------------------------------------------------------------- recovery


async def recovery_pending(db: AsyncSession, resident_id: uuid.UUID) -> bool:
    """Whether this resident is a new phone waiting for an older account."""
    return bool(
        await db.scalar(
            select(
                exists().where(
                    AccountRecovery.new_resident_id == resident_id,
                    AccountRecovery.status.in_(RECOVERY_LIVE),
                )
            )
        )
    )


async def has_activity(db: AsyncSession, resident: Resident) -> bool:
    """A phone with deposits, turns or an email of its own is somebody's account already."""
    if resident.email:
        return True
    deposits = exists().where(DepositSession.resident_id == resident.id)
    bookings = exists().where(Booking.resident_id == resident.id)
    return bool(await db.scalar(select(or_(deposits, bookings))))


async def request_recovery_code(
    db: AsyncSession, settings: Settings, requester_id: uuid.UUID, raw_email: str, now: datetime
) -> dict[str, Any]:
    email = normalize_email(raw_email)
    target = await db.scalar(select(Resident.id).where(Resident.email == email))
    await issue_code(
        db,
        settings,
        purpose="recover",
        email=email,
        requester=requester_id,
        now=now,
        deliver=target is not None and target != requester_id,
    )
    await db.commit()
    return _sent(email)


async def start_recovery(
    db: AsyncSession,
    settings: Settings,
    requester_id: uuid.UUID,
    raw_email: str,
    code: str,
    now: datetime,
    tz: ZoneInfo,
) -> AccountRecovery:
    email = normalize_email(raw_email)
    await check_code(
        db, settings, purpose="recover", email=email, requester=requester_id, code=code, now=now
    )
    target = await db.scalar(select(Resident).where(Resident.email == email).with_for_update())
    requester = await db.get(Resident, requester_id, with_for_update=True)
    if target is None or requester is None or target.id == requester_id:
        raise CodeInvalid("the code expired or was never requested")
    if await has_activity(db, requester):
        raise PhoneInUse("this phone already has deposits or turns of its own")

    mine = await db.scalar(
        select(AccountRecovery).where(
            AccountRecovery.new_resident_id == requester_id,
            AccountRecovery.status.in_(RECOVERY_LIVE),
        )
    )
    if mine is not None:
        if mine.resident_id == target.id:
            await db.commit()
            return mine
        raise RecoveryInProgress("this phone is already recovering another account")

    # A newer, verified request replaces a pending one; the chain does the same (startRecovery).
    previous = await db.scalar(
        select(AccountRecovery)
        .where(
            AccountRecovery.resident_id == target.id,
            AccountRecovery.status.in_(RECOVERY_LIVE),
        )
        .with_for_update()
    )
    if previous is not None:
        previous.status, previous.cancelled_by, previous.updated_at = "cancelled", "replaced", now
        await _notify_cancelled(db, previous, now)
        await db.flush()

    ensure_account(target, settings)
    rec = AccountRecovery(
        id=uuid.uuid4(),
        resident_id=target.id,
        new_resident_id=requester_id,
        account_address=target.address,
        new_owner=requester.owner_address,
        status="starting",
        ready_at=now + RECOVERY_DELAY,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(rec)
    await db.flush()
    when = when_label(rec.ready_at, tz)
    await enqueue(
        db,
        resident_id=target.id,
        kind="recovery_started",
        dedupe_key=f"recovery_started:{rec.id}",
        title="¿Estás cambiando de teléfono?",
        body=(
            "Pidieron pasar tu cuenta a otro teléfono. "
            f"Si no fuiste tú, cancélalo antes del {when}."
        ),
        data={"url": "/account", "recovery_id": str(rec.id)},
        now=now,
    )
    lines = [
        "Alguien que confirmó tu correo pidió pasar tu cuenta de Zyrcle a un teléfono nuevo.",
        f"Si fuiste tú, no tienes que hacer nada: el {when} tu cuenta, tu saldo y tu historial "
        "quedarán en el teléfono nuevo.",
        "Si no fuiste tú, abre Zyrcle en tu teléfono y toca «No fui yo, cancelar» antes de esa "
        "fecha. Mientras tanto tu saldo no se mueve.",
    ]
    await enqueue_email(
        db,
        to=email,
        kind="recovery_started",
        dedupe_key=f"recovery_started:{rec.id}",
        subject=f"Tu cuenta de Zyrcle pasará a otro teléfono el {when}",
        text="\n\n".join(lines) + "\n",
        html_body=render_html("¿Estás cambiando de teléfono?", lines),
        now=now,
    )
    await db.commit()
    return rec


async def cancel_recovery(
    db: AsyncSession, resident_id: uuid.UUID, recovery_id: uuid.UUID, now: datetime
) -> AccountRecovery:
    rec = await db.get(AccountRecovery, recovery_id, with_for_update=True)
    if rec is None or resident_id not in (rec.resident_id, rec.new_resident_id):
        raise NotFound("unknown recovery")
    if rec.status == "cancelling":
        return rec
    if rec.status not in RECOVERY_LIVE:
        raise Conflict(f"the recovery is already {rec.status}")
    rec.status = "cancelling"
    rec.cancelled_by = "owner" if resident_id == rec.resident_id else "new_phone"
    rec.next_attempt_at, rec.updated_at = now, now
    await db.commit()
    return rec


async def _notify_cancelled(db: AsyncSession, rec: AccountRecovery, now: datetime) -> None:
    if rec.new_resident_id and rec.cancelled_by != "new_phone":
        await enqueue(
            db,
            resident_id=rec.new_resident_id,
            kind="recovery_cancelled",
            dedupe_key=f"recovery_cancelled:{rec.id}",
            title="Se canceló la recuperación",
            body="La cuenta que pediste sigue en el teléfono que la tenía.",
            data={"url": "/account", "recovery_id": str(rec.id)},
            now=now,
        )
    target = await db.get(Resident, rec.resident_id)
    if target is not None and target.email and rec.cancelled_by != "replaced":
        lines = [
            "Se canceló el paso de tu cuenta de Zyrcle a otro teléfono.",
            "Tu cuenta y tu saldo siguen en tu teléfono de siempre.",
        ]
        await enqueue_email(
            db,
            to=target.email,
            kind="recovery_cancelled",
            dedupe_key=f"recovery_cancelled:{rec.id}",
            subject="Se canceló el paso de tu cuenta a otro teléfono",
            text="\n\n".join(lines) + "\n",
            html_body=render_html("Recuperación cancelada", lines),
            now=now,
        )


# ---------------------------------------------------------------- views


def recovery_view(rec: AccountRecovery, tz: ZoneInfo) -> dict[str, Any]:
    return {
        "id": str(rec.id),
        "status": rec.status,
        "ready_at": rec.ready_at.isoformat(),
        "ready_label": when_label(rec.ready_at, tz),
        "cancelled_by": rec.cancelled_by,
        "created_at": rec.created_at.isoformat(),
    }


async def account_view(
    db: AsyncSession, settings: Settings, resident_id: uuid.UUID, now: datetime, tz: ZoneInfo
) -> dict[str, Any]:
    resident = await db.get(Resident, resident_id)
    if resident is None:
        raise NotFound("unknown resident")
    incoming = await db.scalar(
        select(AccountRecovery).where(
            AccountRecovery.resident_id == resident_id,
            AccountRecovery.status.in_(RECOVERY_LIVE),
        )
    )
    # This phone's own request, live or recently ended (so the app can say it was cancelled).
    outgoing = await db.scalar(
        select(AccountRecovery)
        .where(
            AccountRecovery.new_resident_id == resident_id,
            or_(
                AccountRecovery.status.in_(RECOVERY_LIVE),
                AccountRecovery.updated_at > now - timedelta(days=3),
            ),
        )
        .order_by(AccountRecovery.created_at.desc())
        .limit(1)
    )
    recovered = await db.scalar(
        select(func.max(AccountRecovery.updated_at)).where(
            AccountRecovery.resident_id == resident_id,
            AccountRecovery.status == "done",
            AccountRecovery.new_owner == resident.owner_address,
        )
    )
    live_outgoing = outgoing is not None and outgoing.status in RECOVERY_LIVE
    return {
        "address": resident.address,
        "owner": resident.owner_address,
        "email": resident.email,
        "email_verified_at": resident.email_verified_at.isoformat()
        if resident.email_verified_at
        else None,
        "email_available": settings.email_enabled,
        "recovery_available": settings.recovery_enabled,
        "can_recover": settings.recovery_enabled
        and not live_outgoing
        and not await has_activity(db, resident),
        "incoming": recovery_view(incoming, tz) if incoming else None,
        "outgoing": recovery_view(outgoing, tz) if outgoing else None,
        "recovered_at": recovered.isoformat() if recovered else None,
    }


# ---------------------------------------------------------------- worker


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
