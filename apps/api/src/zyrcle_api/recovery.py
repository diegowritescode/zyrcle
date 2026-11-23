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

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .chain import account_address
from .config import Settings
from .email_codes import DAY, _sent, check_code, issue_code, normalize_email
from .errors import (
    CodeInvalid,
    Conflict,
    NotFound,
    PhoneInUse,
    RecoveryInProgress,
)
from .mail import enqueue_email, render_html
from .models import (
    RECOVERY_LIVE,
    AccountRecovery,
    Booking,
    DepositSession,
    Resident,
)
from .notifications import enqueue

log = logging.getLogger(__name__)

# ZyrcleAccount.RECOVERY_DELAY. Only an estimate here: the chain's readyAt is what counts.
RECOVERY_DELAY = timedelta(hours=48)
LEASE = timedelta(minutes=2)  # how long a claimed recovery is left alone by other workers

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


def when_label(at: datetime, tz: ZoneInfo) -> str:
    """'sábado 28 de noviembre, 3:15 p. m.' (built by hand: Intl differs between runtimes)."""
    t = at.astimezone(tz)
    hour = t.hour % 12 or 12
    suffix = "m." if t.hour == 12 and t.minute == 0 else ("a. m." if t.hour < 12 else "p. m.")
    day = f"{_WEEKDAYS[t.weekday()]} {t.day} de {_MONTHS[t.month - 1]}"
    return f"{day}, {hour}:{t.minute:02d} {suffix}"


def ensure_account(resident: Resident, settings: Settings) -> None:
    """Give a resident from before smart accounts (address == owner) their account address."""
    factory = settings.account_factory_address
    if settings.accounts_enabled and factory and resident.address == resident.owner_address:
        resident.address = account_address(factory, resident.owner_address)


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
        # `when` ends in "a. m." or "p. m.": no period after it.
        body=f"Tu cuenta pasará a otro teléfono el {when} Si no fuiste tú, cancélalo ya.",
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
    # A recovery that ended in the last day, so the new phone can say it worked.
    recovered = await db.scalar(
        select(func.max(AccountRecovery.updated_at)).where(
            AccountRecovery.resident_id == resident_id,
            AccountRecovery.status == "done",
            AccountRecovery.new_owner == resident.owner_address,
            AccountRecovery.updated_at > now - DAY,
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
