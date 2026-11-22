"""Demo routes: let a visitor play the part of the resident in front of a simulated container.

Mounted only when ZYRCLE_DEMO_SIMULATOR_URL is set. A real resident scans the QR on a physical
container and drops material into it; here the page reads the QR from the API and asks the
simulator to drop the items. The drop goes through the API so it can check the visitor owns the
session.
"""

import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from zyrcle_protocol import qr_payload

from .api import Resident, Service
from .auth import utcnow
from .domain.session_machine import State
from .models import Container, Device
from .public import busy_containers, is_online

router = APIRouter(prefix="/v1/demo", tags=["demo"])


def simulator_dep(request: Request) -> httpx.AsyncClient:
    return request.app.state.simulator


Simulator = Annotated[httpx.AsyncClient, Depends(simulator_dep)]


class DropIn(BaseModel):
    item: str = Field(max_length=40)
    count: int = Field(default=1, ge=1, le=20)


@router.get("/containers")
async def containers(request: Request) -> list[dict[str, Any]]:
    now = utcnow()
    settings = request.app.state.settings
    async with request.app.state.maker() as db:
        rows = (await db.execute(select(Container, Device).join(Device))).all()
        busy = await busy_containers(db)
    out = []
    for container, device in rows:
        online = is_online(device, now, settings)
        code_ok = bool(
            device.current_code and device.code_expires_at and device.code_expires_at > now
        )
        out.append(
            {
                "id": container.id,
                "name": container.name,
                "accepted_materials": container.accepted_materials,
                "online": online,
                "busy": container.id in busy,
                "qr": qr_payload(container.id, device.current_code) if online and code_ok else None,
            }
        )
    return sorted(out, key=lambda c: c["id"])


@router.get("/items")
async def items(simulator: Simulator) -> list[dict[str, Any]]:
    r = await simulator.get("/items")
    r.raise_for_status()
    return r.json()


@router.post("/sessions/{session_id}/drop")
async def drop(
    session_id: uuid.UUID,
    body: DropIn,
    resident: Resident,
    service: Service,
    simulator: Simulator,
    request: Request,
) -> dict[str, Any]:
    session = await service.get(session_id)
    if session.resident_id != resident:
        raise HTTPException(404, {"code": "not_found", "detail": "unknown session"})
    if session.state not in (State.OPEN.value, State.DEPOSITING.value):
        raise HTTPException(409, {"code": "conflict", "detail": "the lid is not open"})
    async with request.app.state.maker() as db:
        container = await db.get(Container, session.container_id)
    assert container is not None
    r = await simulator.post(
        f"/containers/{container.device_id}/deposit", json={"item": body.item, "count": body.count}
    )
    if r.status_code != 200:
        raise HTTPException(r.status_code, {"code": "simulator", "detail": r.json().get("detail")})
    return {"ok": True}
