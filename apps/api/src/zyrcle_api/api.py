import asyncio
import logging
import secrets
import uuid
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from zyrcle_protocol import load_public_key

from . import auth
from .bookings import site_schedule
from .chain import WEI_PER_COP
from .config import Settings
from .errors import SessionError
from .models import (
    Collector,
    Container,
    DepositSession,
    Device,
    Host,
    MaterialPrice,
    Payout,
    PushToken,
    Site,
)
from .models import Resident as ResidentRow
from .sessions import MATERIALS, SessionService, session_view

router = APIRouter()
log = logging.getLogger(__name__)


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


def operator_dep(
    settings: Annotated[Settings, Depends(settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not secrets.compare_digest(_bearer(authorization), settings.operator_token):
        raise HTTPException(401, "invalid operator token")
    return "operator"


def _raise(e: SessionError) -> None:
    raise HTTPException(e.status, {"code": e.code, "detail": e.detail}) from None


Resident = Annotated[uuid.UUID, Depends(resident_dep)]
Operator = Annotated[str, Depends(operator_dep)]
Service = Annotated[SessionService, Depends(service_dep)]


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
        resident = auth.read_token(app.state.settings, websocket.query_params.get("token", ""))
        session = await app.state.sessions.get(session_id)
    except (auth.AuthError, SessionError):
        await websocket.close(code=4401)
        return
    if session.resident_id != resident:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = app.state.hub.subscribe(str(session_id))
    try:
        await websocket.send_json({"type": "state", **session_view(session)})
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
        # Set when the operator named this participant a collector (docs/adr/0012).
        "collector": collector.name if collector is not None and collector.active else None,
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
            }
            for s, name, p in deposits
        ],
    }


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


# ---------------------------------------------------------------- operator


class ScheduleIn(BaseModel):
    """Opening hours in local time, as whole hours [opens_hour, closes_hour), and residents per
    container per hour (docs/adr/0009)."""

    opens_hour: int = Field(default=0, ge=0, le=23)
    closes_hour: int = Field(default=24, ge=1, le=24)
    slot_capacity: int = Field(default=20, ge=1, le=1000)

    @model_validator(mode="after")
    def _ordered(self) -> "ScheduleIn":
        if self.opens_hour >= self.closes_hour:
            raise ValueError("opens_hour must be before closes_hour")
        return self


class HostIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["university", "residential", "business", "public"]
    payout_address: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{40}$")


class SiteIn(ScheduleIn):
    host_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)


class DeviceIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,64}$")
    public_key_pem: str = Field(max_length=1000)


class ContainerIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,64}$")
    site_id: uuid.UUID
    device_id: str
    name: str = Field(max_length=200)
    accepted_materials: list[str] = Field(min_length=1)
    area_mm2: int = Field(gt=0)
    depth_mm: int = Field(gt=0)


class ReviewIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=1000)


def host_view(h: Host) -> dict[str, Any]:
    return {
        "id": str(h.id),
        "name": h.name,
        "kind": h.kind,
        "payout_address": h.payout_address,
    }


@router.post("/v1/operator/hosts", status_code=201)
async def create_host(body: HostIn, _: Operator, request: Request) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        h = Host(
            id=uuid.uuid4(),
            name=body.name,
            kind=body.kind,
            payout_address=body.payout_address.lower() if body.payout_address else None,
        )
        db.add(h)
        await db.commit()
    return host_view(h)


@router.post("/v1/operator/sites", status_code=201)
async def create_site(body: SiteIn, _: Operator, request: Request) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        if await db.get(Host, body.host_id) is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown host"})
        site = Site(id=uuid.uuid4(), **body.model_dump())
        db.add(site)
        await db.commit()
    return site_schedule(site)


@router.put("/v1/operator/sites/{site_id}/schedule")
async def set_schedule(
    site_id: uuid.UUID, body: ScheduleIn, _: Operator, request: Request
) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        site = await db.get(Site, site_id, with_for_update=True)
        if site is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown site"})
        site.opens_hour, site.closes_hour = body.opens_hour, body.closes_hour
        site.slot_capacity = body.slot_capacity
        await db.commit()
        return site_schedule(site)


@router.post("/v1/operator/devices", status_code=201)
async def register_device(body: DeviceIn, _: Operator, request: Request) -> dict[str, str]:
    try:
        load_public_key(body.public_key_pem)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    async with request.app.state.maker() as db:
        if await db.get(Device, body.id):
            raise HTTPException(409, "device already registered")
        db.add(Device(id=body.id, public_key_pem=body.public_key_pem))
        await db.commit()
    return {"id": body.id}


@router.post("/v1/operator/containers", status_code=201)
async def create_container(body: ContainerIn, _: Operator, request: Request) -> dict[str, str]:
    unknown = set(body.accepted_materials) - set(MATERIALS)
    if unknown:
        raise HTTPException(422, f"unknown materials: {sorted(unknown)}")
    async with request.app.state.maker() as db:
        if await db.get(Site, body.site_id) is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown site"})
        db.add(Container(**body.model_dump()))
        await db.commit()
    return {"id": body.id}


@router.get("/v1/operator/review")
async def review_queue(_: Operator, service: Service) -> list[dict[str, Any]]:
    return await service.review_queue()


@router.post("/v1/operator/sessions/{session_id}/review")
async def review(
    session_id: uuid.UUID, body: ReviewIn, operator: Operator, service: Service
) -> dict[str, Any]:
    try:
        return await service.review(session_id, body.approve, operator, body.note)
    except SessionError as e:
        _raise(e)
        raise


class PriceIn(BaseModel):
    cop_per_kg: int = Field(ge=0, le=1_000_000)


@router.put("/v1/operator/prices/{material}")
async def set_price(material: str, body: PriceIn, _: Operator, request: Request) -> dict[str, Any]:
    if material not in MATERIALS:
        raise HTTPException(422, f"unknown material {material!r}")
    async with request.app.state.maker() as db:
        price = await db.get(MaterialPrice, material)
        if price is None:
            price = MaterialPrice(material=material, cop_per_kg=body.cop_per_kg, source="manual")
            db.add(price)
        else:
            price.cop_per_kg, price.source = body.cop_per_kg, "manual"
            price.updated_at = auth.utcnow()
        await db.commit()
    return {"material": material, "cop_per_kg": body.cop_per_kg, "source": "manual"}


@router.get("/v1/operator/treasury")
async def treasury(_: Operator, request: Request) -> dict[str, Any]:
    chain = request.app.state.chain
    if chain is None:
        raise HTTPException(503, "chain is not configured")
    state = await chain.state()
    return {"address": chain.treasury.address, **state.__dict__}
