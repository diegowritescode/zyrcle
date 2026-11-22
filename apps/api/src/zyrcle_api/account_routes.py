"""Resident endpoints for the recovery email and lost-phone recovery
(docs/adr/0010-smart-accounts-and-recovery.md)."""

import uuid
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import recovery
from .api import Resident
from .auth import utcnow
from .config import Settings
from .errors import RecoveryUnavailable, SessionError

router = APIRouter(prefix="/v1", tags=["account"])


class EmailIn(BaseModel):
    email: str = Field(max_length=254)


class CodeIn(EmailIn):
    code: str = Field(min_length=6, max_length=12)


def _http(e: SessionError) -> HTTPException:
    return HTTPException(e.status, {"code": e.code, "detail": e.detail})


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _tz(request: Request) -> ZoneInfo:
    return ZoneInfo(_settings(request).timezone)


def _need(enabled: bool, what: str) -> None:
    if not enabled:
        raise _http(RecoveryUnavailable(f"{what} is not configured on this server"))


@router.get("/me/account")
async def my_account(resident: Resident, request: Request) -> dict[str, Any]:
    """Recovery email, and any recovery this resident is part of: someone moving their account to
    another phone (`incoming`), or this phone waiting for an older account (`outgoing`)."""
    async with request.app.state.maker() as db:
        try:
            return await recovery.account_view(
                db, _settings(request), resident, utcnow(), _tz(request)
            )
        except SessionError as e:
            raise _http(e) from None


@router.post("/me/email", status_code=202)
async def send_email_code(body: EmailIn, resident: Resident, request: Request) -> dict[str, Any]:
    _need(_settings(request).email_enabled, "email")
    async with request.app.state.maker() as db:
        try:
            return await recovery.request_email_code(
                db, _settings(request), resident, body.email, utcnow()
            )
        except SessionError as e:
            raise _http(e) from None


@router.post("/me/email/verify")
async def verify_email(body: CodeIn, resident: Resident, request: Request) -> dict[str, Any]:
    _need(_settings(request).email_enabled, "email")
    async with request.app.state.maker() as db:
        try:
            return await recovery.verify_email(
                db, _settings(request), resident, body.email, body.code, utcnow()
            )
        except SessionError as e:
            raise _http(e) from None


@router.post("/recovery/code", status_code=202)
async def send_recovery_code(body: EmailIn, resident: Resident, request: Request) -> dict[str, Any]:
    """Email a code if an account uses that address. The answer is the same either way."""
    _need(_settings(request).recovery_enabled, "account recovery")
    async with request.app.state.maker() as db:
        try:
            return await recovery.request_recovery_code(
                db, _settings(request), resident, body.email, utcnow()
            )
        except SessionError as e:
            raise _http(e) from None


@router.post("/recovery", status_code=201)
async def start_recovery(body: CodeIn, resident: Resident, request: Request) -> dict[str, Any]:
    _need(_settings(request).recovery_enabled, "account recovery")
    async with request.app.state.maker() as db:
        try:
            rec = await recovery.start_recovery(
                db, _settings(request), resident, body.email, body.code, utcnow(), _tz(request)
            )
        except SessionError as e:
            raise _http(e) from None
        return recovery.recovery_view(rec, _tz(request))


@router.delete("/recovery/{recovery_id}")
async def cancel_recovery(
    recovery_id: uuid.UUID, resident: Resident, request: Request
) -> dict[str, Any]:
    """Either side may cancel: the account's owner ("no fui yo") or the phone that asked."""
    async with request.app.state.maker() as db:
        try:
            rec = await recovery.cancel_recovery(db, resident, recovery_id, utcnow())
        except SessionError as e:
            raise _http(e) from None
        return recovery.recovery_view(rec, _tz(request))
