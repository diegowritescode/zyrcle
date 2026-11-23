"""What every route depends on: settings, the session service, and who is calling (a resident's
session or an operator, docs/adr/0014)."""

import uuid
from typing import Annotated

from fastapi import (
    Depends,
    Header,
    HTTPException,
    Request,
)
from sqlalchemy import select

from . import auth
from .config import Settings
from .errors import SessionError
from .models import Resident as ResidentRow
from .operator_auth import Who, operator_who
from .sessions import SessionService


def settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def service_dep(request: Request) -> SessionService:
    return request.app.state.sessions


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    return authorization.removeprefix("Bearer ")


async def resident_dep(
    request: Request,
    settings: Annotated[Settings, Depends(settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    try:
        resident_id, key = auth.read_claims(settings, _bearer(authorization))
    except auth.AuthError as e:
        raise HTTPException(401, str(e)) from None
    # The key must still own the account: a recovery ends the old phone's session right away, and
    # a resident folded into an account (the new phone's) no longer exists.
    async with request.app.state.maker() as db:
        owner = await db.scalar(
            select(ResidentRow.owner_address).where(ResidentRow.id == resident_id)
        )
    if owner is None or (key is not None and key != owner):
        raise HTTPException(401, "session ended: sign in again")
    return resident_id


async def operator_dep(who: Annotated[Who, Depends(operator_who)]) -> str:
    """Who is acting: an operator's email, or "token" for the shared token (docs/adr/0014)."""
    return who.name


def _raise(e: SessionError) -> None:
    raise HTTPException(e.status, {"code": e.code, "detail": e.detail}) from None


Resident = Annotated[uuid.UUID, Depends(resident_dep)]
Operator = Annotated[str, Depends(operator_dep)]
Service = Annotated[SessionService, Depends(service_dep)]
