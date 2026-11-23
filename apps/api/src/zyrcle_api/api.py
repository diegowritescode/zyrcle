import asyncio
import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from . import auth
from .chain import WEI_PER_COP
from .config import Settings
from .deps import Resident, Service, _raise, settings_dep
from .errors import SessionError
from .models import (
    Collector,
    Container,
    DepositSession,
    Merchant,
    Payout,
    PushToken,
    Settlement,
)
from .models import Resident as ResidentRow
from .sessions import MATERIALS, session_view

router = APIRouter()
log = logging.getLogger(__name__)


# ---------------------------------------------------------------- health


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        await db.execute(text("select 1"))
    return {"ok": True, "mqtt": request.app.state.bridge.connected.is_set()}


# ---------------------------------------------------------------- auth


class VerifyIn(BaseModel):
    message: str = Field(max_length=2000)
    signature: str = Field(max_length=200)


@router.post("/v1/auth/nonce")
async def nonce(request: Request) -> dict[str, str]:
    async with request.app.state.maker() as db:
        n = await auth.new_nonce(db, auth.utcnow())
    return {"nonce": n.nonce, "expires_at": n.expires_at.isoformat()}


@router.post("/v1/auth/verify")
async def verify(
    body: VerifyIn, request: Request, settings: Annotated[Settings, Depends(settings_dep)]
) -> dict[str, str]:
    now = auth.utcnow()
    async with request.app.state.maker() as db:
        try:
            resident = await auth.verify_siwe(db, settings, body.message, body.signature, now)
        except auth.KeyRetired as e:
            raise HTTPException(403, {"code": "key_retired", "detail": str(e)}) from None
        except auth.AuthError as e:
            raise HTTPException(401, str(e)) from None
    return {
        "token": auth.issue_token(settings, resident, now),
        "resident_id": str(resident.id),
        # Where the resident's ZYR lives (their account) and the key that controls it.
        "address": resident.address,
        "owner": resident.owner_address,
    }


# ---------------------------------------------------------------- resident sessions


class StartIn(BaseModel):
    qr: str = Field(max_length=200)
    material: str


@router.get("/v1/materials")
async def materials() -> list[str]:
    return MATERIALS


@router.post("/v1/sessions", status_code=201)
async def start_session(body: StartIn, resident: Resident, service: Service) -> dict[str, Any]:
    try:
        return await service.start(resident, body.qr, body.material)
    except SessionError as e:
        _raise(e)
        raise


@router.get("/v1/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID, resident: Resident, service: Service
) -> dict[str, Any]:
    try:
        session = await service.get(session_id)
    except SessionError as e:
        _raise(e)
        raise
    if session.resident_id != resident:
        raise HTTPException(404, {"code": "not_found", "detail": "unknown session"})
    return session_view(session)


@router.post("/v1/sessions/{session_id}/finish")
async def finish_session(
    session_id: uuid.UUID, resident: Resident, service: Service
) -> dict[str, Any]:
    try:
        return await service.finish(session_id, resident)
    except SessionError as e:
        _raise(e)
        raise


@router.websocket("/v1/sessions/{session_id}/live")
async def live(websocket: WebSocket, session_id: uuid.UUID) -> None:
    """Live readings and state changes. Auth: ?token=<JWT> (browsers cannot set WS headers)."""
    app = websocket.app
    try:
        resident, key = auth.read_claims(
            app.state.settings, websocket.query_params.get("token", "")
        )
        session = await app.state.sessions.get(session_id)
    except (auth.AuthError, SessionError):
        await websocket.close(code=4401)
        return
    # Like resident_dep: a key whose account moved to another phone has no session any more.
    async with app.state.maker() as db:
        owner = await db.scalar(select(ResidentRow.owner_address).where(ResidentRow.id == resident))
    if owner is None or (key is not None and key != owner):
        await websocket.close(code=4401)
        return
    if session.resident_id != resident:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = app.state.hub.subscribe(str(session_id))
    try:
        await websocket.send_json({"type": "state", **session_view(session)})
        if session.state not in ("authorized", "open", "depositing", "closing"):
            await websocket.close()  # nothing more will happen to a finished session
            return
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") == "state" and event.get("state") not in (
                "authorized",
                "open",
                "depositing",
                "closing",
            ):
                await websocket.close()
                return
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        app.state.hub.unsubscribe(str(session_id), queue)


@router.get("/v1/me")
async def me(resident: Resident, request: Request) -> dict[str, Any]:
    """The resident's wallet, on-chain ZYR balance (shown as pesos), payouts and deposits."""
    async with request.app.state.maker() as db:
        row = await db.get(ResidentRow, resident)
        if row is None:
            raise HTTPException(404, "unknown resident")
        payouts = list(
            await db.scalars(
                select(Payout)
                .join(DepositSession, DepositSession.id == Payout.session_id)
                .where(DepositSession.resident_id == resident)
                .order_by(Payout.created_at.desc())
                .limit(50)
            )
        )
        deposits = (
            await db.execute(
                select(DepositSession, Container.name, Payout)
                .join(Container, Container.id == DepositSession.container_id)
                .outerjoin(Payout, Payout.session_id == DepositSession.id)
                .where(DepositSession.resident_id == resident)
                .order_by(DepositSession.created_at.desc())
                .limit(20)
            )
        ).all()
        collector = await db.get(Collector, resident)
        merchant = await db.get(Merchant, resident)
        # What each deposit got when its bag was sold (docs/adr/0013), on top of the advance.
        settled = {
            ref: paid
            for ref, paid in await db.execute(
                select(Settlement.party_ref, Settlement.paid_cop).where(
                    Settlement.party == "deposit",
                    Settlement.party_ref.in_([str(s.id) for s, _, _ in deposits]),
                    Settlement.paid_cop.is_not(None),
                )
            )
        }
    chain = request.app.state.chain
    balance = None
    if chain is not None:
        try:
            balance = await chain.balance_wei(row.address)
        except Exception as e:  # the chain being unreachable must not break the resident's page
            log.warning("could not read balance of %s: %s", row.address, e)
    return {
        "resident_id": str(row.id),
        "address": row.address,
        "owner": row.owner_address,
        "email": row.email,
        # Ley 1581: the policy version they accepted, and the one in force (docs/adr/0028).
        "privacy_version": row.privacy_version,
        "privacy_current": request.app.state.settings.privacy_version,
        # Set when the operator named this participant a collector (docs/adr/0012).
        "collector": collector.name if collector is not None and collector.active else None,
        # Set when the operator named this participant a merchant (docs/adr/0029).
        "merchant": merchant.name if merchant is not None and merchant.active else None,
        "balance_cop": None if balance is None else balance / WEI_PER_COP,
        "payouts": [
            {
                "session_id": str(p.session_id),
                "kind": p.kind,
                "amount_cop": p.amount_cop,
                "status": p.status,
                "tx_hash": p.tx_hash,
                "created_at": p.created_at.isoformat(),
            }
            for p in payouts
        ],
        "sessions": [
            {
                **session_view(s),
                "container_name": name,
                "payout": None
                if p is None
                else {"amount_cop": p.amount_cop, "status": p.status, "tx_hash": p.tx_hash},
                "settled_cop": settled.get(str(s.id)),
            }
            for s, name, p in deposits
        ],
    }


class ConsentIn(BaseModel):
    version: str = Field(max_length=16)


@router.post("/v1/me/consent")
async def consent(body: ConsentIn, resident: Resident, request: Request) -> dict[str, Any]:
    """The participant accepts the data-processing policy in force (Ley 1581 de 2012)."""
    settings: Settings = request.app.state.settings
    if body.version != settings.privacy_version:
        raise HTTPException(
            409, {"code": "conflict", "detail": "that is not the policy in force; reload it"}
        )
    async with request.app.state.maker() as db:
        row = await db.get(ResidentRow, resident, with_for_update=True)
        assert row is not None
        row.privacy_version, row.privacy_accepted_at = body.version, auth.utcnow()
        await db.commit()
        return {"privacy_version": row.privacy_version}


class PushTokenIn(BaseModel):
    token: str = Field(max_length=200, pattern=r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]{8,}\]$")
    platform: Literal["ios", "android"]


@router.put("/v1/me/push-token", status_code=204)
async def register_push_token(body: PushTokenIn, resident: Resident, request: Request) -> None:
    """Where to push this resident's notifications (docs/adr/0008). The app calls it on every
    start; a token registered by another wallet moves to this one."""
    now = auth.utcnow()
    async with request.app.state.maker() as db:
        await db.execute(
            insert(PushToken)
            .values(
                token=body.token,
                resident_id=resident,
                platform=body.platform,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["token"],
                set_={
                    "resident_id": resident,
                    "platform": body.platform,
                    "updated_at": now,
                    "disabled_at": None,
                },
            )
        )
        await db.commit()
