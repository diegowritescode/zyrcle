"""Operator accounts and their sign-in by email code (docs/adr/0014).

`operator_dep` accepts an operator's session token, or the shared operator token that deploy
scripts, the seed and the tests use (an admin named "token"). Routes record `who` on everything an
operator does.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from .auth import utcnow
from .config import Settings
from .email_codes import mask_email, normalize_email
from .mail import CODE_TTL, enqueue_email, render_html
from .models import Operator as OperatorRow
from .models import OperatorCode

router = APIRouter(prefix="/v1/operator", tags=["operators"])

RESEND_AFTER = timedelta(seconds=60)
CODES_PER_DAY = 10
MAX_ATTEMPTS = 5
DAY = timedelta(days=1)


@dataclass(frozen=True)
class Who:
    """The operator behind a request: their email (or "token" for the shared token) and role."""

    name: str
    role: str
    operator_id: uuid.UUID | None = None

    @property
    def admin(self) -> bool:
        return self.role == "admin"


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    return authorization.removeprefix("Bearer ")


def issue_operator_token(settings: Settings, op: OperatorRow, now: datetime) -> str:
    claims = {
        "sub": str(op.id),
        "role": "operator",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.operator_jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


async def operator_who(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Who:
    settings: Settings = request.app.state.settings
    token = _bearer(authorization)
    if secrets.compare_digest(token, settings.operator_token):
        return Who("token", "admin")
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid operator token") from None
    if claims.get("role") != "operator":
        raise HTTPException(401, "invalid operator token")
    async with request.app.state.maker() as db:
        op = await db.get(OperatorRow, uuid.UUID(claims["sub"]))
    if op is None or not op.active:
        raise HTTPException(401, "this operator account is not active")
    return Who(op.email, op.role, op.id)


async def admin_who(who: Annotated[Who, Depends(operator_who)]) -> Who:
    if not who.admin:
        raise HTTPException(403, {"code": "forbidden", "detail": "only admins can do this"})
    return who


OperatorWho = Annotated[Who, Depends(operator_who)]
AdminWho = Annotated[Who, Depends(admin_who)]


def _hash(settings: Settings, email: str, code: str) -> str:
    key = settings.jwt_secret.encode()
    return hmac.new(key, f"operator|{email}|{code}".encode(), hashlib.sha256).hexdigest()


def operator_view(op: OperatorRow) -> dict[str, Any]:
    return {
        "id": str(op.id),
        "email": op.email,
        "name": op.name,
        "role": op.role,
        "active": op.active,
        "last_login_at": op.last_login_at.isoformat() if op.last_login_at else None,
    }


class EmailIn(BaseModel):
    email: str = Field(max_length=254)


class LoginIn(EmailIn):
    code: str = Field(min_length=6, max_length=12)


class OperatorIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "operator"] = "operator"


class OperatorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Literal["admin", "operator"] | None = None
    active: bool | None = None


def _email(raw: str) -> str:
    try:
        return normalize_email(raw)
    except Exception:
        raise HTTPException(
            422, {"code": "invalid_email", "detail": "that is not an email"}
        ) from None


@router.post("/login/code", status_code=202)
async def request_code(body: EmailIn, request: Request) -> dict[str, Any]:
    """Email a sign-in code. Answers the same whether or not the address is an operator's."""
    settings: Settings = request.app.state.settings
    email, now = _email(body.email), utcnow()
    async with request.app.state.maker() as db:
        recent = list(
            await db.scalars(
                select(OperatorCode.created_at)
                .where(OperatorCode.email == email, OperatorCode.created_at > now - DAY)
                .order_by(OperatorCode.created_at.desc())
            )
        )
        if recent and recent[0] > now - RESEND_AFTER:
            wait = int((recent[0] + RESEND_AFTER - now).total_seconds()) + 1
            raise HTTPException(
                429, {"code": "too_soon", "detail": f"wait {wait} seconds for another code"}
            )
        if len(recent) >= CODES_PER_DAY:
            raise HTTPException(429, {"code": "too_many_codes", "detail": "too many codes today"})
        op = await db.scalar(select(OperatorRow).where(OperatorRow.email == email))
        await db.execute(
            update(OperatorCode)
            .where(OperatorCode.email == email, OperatorCode.used_at.is_(None))
            .values(used_at=now)
        )
        code = f"{secrets.randbelow(10**6):06d}"
        row = OperatorCode(
            id=uuid.uuid4(),
            email=email,
            code_hash=_hash(settings, email, code),
            expires_at=now + CODE_TTL,
            created_at=now,
        )
        db.add(row)
        # With email off the code is never sent, so it is not written to the outbox either.
        if op is not None and op.active and settings.email_enabled:
            title = "Tu código para entrar a la consola de Zyrcle"
            paragraphs = [
                "Escribe este código en la consola de operación:",
                "Vence en 10 minutos. Si no fuiste tú, ignora este correo.",
            ]
            await enqueue_email(
                db,
                to=email,
                kind="code_operator",
                dedupe_key=f"code_operator:{row.id}",
                subject=title,
                text=f"{paragraphs[0]} {code}\n\n{paragraphs[1]}",
                html_body=render_html(title, paragraphs, code),
                now=now,
            )
        await db.commit()
    return {
        "sent_to": mask_email(email),
        "expires_in_s": int(CODE_TTL.total_seconds()),
        "resend_in_s": int(RESEND_AFTER.total_seconds()),
    }


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    email, now = _email(body.email), utcnow()
    async with request.app.state.maker() as db:
        row = await db.scalar(
            select(OperatorCode)
            .where(
                OperatorCode.email == email,
                OperatorCode.used_at.is_(None),
                OperatorCode.expires_at > now,
            )
            .order_by(OperatorCode.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        wrong = HTTPException(401, {"code": "code_invalid", "detail": "wrong or expired code"})
        if row is None:
            raise wrong
        if not hmac.compare_digest(row.code_hash, _hash(settings, email, body.code.strip())):
            row.attempts += 1
            if row.attempts >= MAX_ATTEMPTS:
                row.used_at = now
            await db.commit()
            raise wrong
        op = await db.scalar(select(OperatorRow).where(OperatorRow.email == email))
        row.used_at = now
        if op is None or not op.active:
            await db.commit()
            raise wrong
        op.last_login_at = now
        await db.commit()
        return {"token": issue_operator_token(settings, op, now), "operator": operator_view(op)}


@router.get("/me")
async def me(who: OperatorWho) -> dict[str, Any]:
    return {
        "name": who.name,
        "role": who.role,
        "id": str(who.operator_id) if who.operator_id else None,
    }


@router.get("/operators")
async def list_operators(_: AdminWho, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        return [
            operator_view(o)
            for o in await db.scalars(select(OperatorRow).order_by(OperatorRow.created_at))
        ]


@router.post("/operators", status_code=201)
async def add_operator(body: OperatorIn, _: AdminWho, request: Request) -> dict[str, Any]:
    email = _email(body.email)
    async with request.app.state.maker() as db:
        taken = await db.scalar(
            select(func.count()).select_from(OperatorRow).where(OperatorRow.email == email)
        )
        if taken:
            raise HTTPException(409, {"code": "conflict", "detail": "that email is an operator"})
        op = OperatorRow(id=uuid.uuid4(), email=email, name=body.name, role=body.role, active=True)
        db.add(op)
        await db.commit()
        return operator_view(op)


@router.patch("/operators/{operator_id}")
async def update_operator(
    operator_id: uuid.UUID, body: OperatorPatch, who: AdminWho, request: Request
) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        op = await db.get(OperatorRow, operator_id, with_for_update=True)
        if op is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown operator"})
        if op.id == who.operator_id and (body.active is False or body.role == "operator"):
            raise HTTPException(
                409, {"code": "conflict", "detail": "you cannot demote or deactivate yourself"}
            )
        if body.name is not None:
            op.name = body.name
        if body.role is not None:
            op.role = body.role
        if body.active is not None:
            op.active = body.active
        await db.commit()
        return operator_view(op)
