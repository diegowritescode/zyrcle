"""Emailed six-digit codes and the participant's recovery email (docs/adr/0010).

A code proves the participant reads an address: to confirm their recovery email, and later to
recover their account on a new phone (recovery.py). Codes are stored as an HMAC, expire with the
email (`CODE_TTL`), allow five guesses, and are rate limited per address, purpose and participant.
"""

import hashlib
import hmac
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .errors import (
    CodeInvalid,
    EmailTaken,
    InvalidEmail,
    NotFound,
    TooManyCodes,
    TooSoon,
)
from .mail import CODE_TTL, enqueue_email, render_html
from .models import (
    EmailCode,
    Resident,
)

log = logging.getLogger(__name__)

RESEND_AFTER = timedelta(seconds=60)
CODES_PER_DAY = 5  # per email address and purpose
CODES_PER_REQUESTER = 10  # per resident and day, whatever the addresses
MAX_CODE_ATTEMPTS = 5
DAY = timedelta(days=1)

_EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise InvalidEmail("that does not look like an email address")
    return email


def mask_email(email: str) -> str:
    """d•••@gmail.com: enough for the resident to recognise it, not enough to harvest it."""
    local, _, domain = email.partition("@")
    return f"{local[0]}•••@{domain}"


def _hash(settings: Settings, purpose: str, email: str, requester: uuid.UUID, code: str) -> str:
    message = f"{purpose}|{email}|{requester}|{code}".encode()
    return hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()


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
