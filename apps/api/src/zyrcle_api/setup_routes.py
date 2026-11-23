"""Operator routes that set the system up: hosts, sites and their schedules, devices, containers,
reference prices, the review queue, and the operator's views of health and the Treasury."""

import logging
import uuid
from typing import Any, Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
)
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from zyrcle_protocol import load_public_key

from . import auth
from .bookings import site_schedule
from .deps import Operator, Service, _raise
from .errors import SessionError
from .models import (
    Container,
    Device,
    Host,
    MaterialPrice,
    Site,
)
from .sessions import MATERIALS

router = APIRouter()
log = logging.getLogger(__name__)


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
        if await db.get(Device, body.device_id) is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown device"})
        if await db.get(Container, body.id) is not None:
            raise HTTPException(409, {"code": "conflict", "detail": "that container id exists"})
        taken = await db.scalar(select(Container.id).where(Container.device_id == body.device_id))
        if taken is not None:
            raise HTTPException(
                409, {"code": "conflict", "detail": f"that device is already container {taken}"}
            )
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


@router.get("/v1/operator/prices")
async def list_prices(_: Operator, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        prices = {p.material: p for p in await db.scalars(select(MaterialPrice))}
    return [
        {
            "material": m,
            "cop_per_kg": prices[m].cop_per_kg if m in prices else None,
            "source": prices[m].source if m in prices else None,
        }
        for m in MATERIALS
    ]


@router.get("/v1/operator/sites")
async def list_sites(_: Operator, request: Request) -> list[dict[str, Any]]:
    """Every site with its schedule and host, for the console."""
    async with request.app.state.maker() as db:
        rows = await db.execute(select(Site, Host).join(Host).order_by(Host.name, Site.name))
        return [{**site_schedule(site), "host_name": host.name} for site, host in rows]


@router.get("/v1/operator/health")
async def operator_health(_: Operator, request: Request) -> dict[str, Any]:
    """Outboxes, devices, broker, chain, Treasury and gas keys, with warnings (docs/adr/0028)."""
    return await request.app.state.health()


@router.get("/v1/operator/treasury")
async def treasury(_: Operator, request: Request) -> dict[str, Any]:
    chain = request.app.state.chain
    if chain is None:
        raise HTTPException(503, "chain is not configured")
    state = await chain.state()
    return {"address": chain.treasury.address, **state.__dict__}
