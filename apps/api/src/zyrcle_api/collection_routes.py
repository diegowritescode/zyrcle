"""Collector and operator endpoints for collections, bags and incidents (docs/adr/0012)."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from .auth import utcnow
from .collection import CollectionService, bag_view, new_bag_code
from .deps import Operator, Resident
from .errors import SessionError
from .models import Bag, Collection, Collector, Container, Incident, SaleLine
from .models import Resident as ResidentRow
from .sessions import MATERIALS

router = APIRouter(prefix="/v1", tags=["collection"])


def collections_dep(request: Request) -> CollectionService:
    return request.app.state.collections


Collections = Annotated[CollectionService, Depends(collections_dep)]


def _http(e: SessionError) -> HTTPException:
    return HTTPException(e.status, {"code": e.code, "detail": e.detail})


class StartIn(BaseModel):
    qr: str = Field(max_length=200)


class FillIn(BaseModel):
    """The bag being filled (its QR or code); null takes out residue instead."""

    bag: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------- collector


@router.get("/collector")
async def collector_home(
    resident: Resident, collections: Collections, request: Request
) -> dict[str, Any]:
    """What the collector screen shows: who they are, their collection in progress, their bags."""
    async with request.app.state.maker() as db:
        collector = await db.get(Collector, resident)
    if collector is None or not collector.active:
        raise HTTPException(403, {"code": "forbidden", "detail": "not a collector"})
    return {
        "name": collector.name,
        "current": await collections.current(resident),
        "bags": await collections.my_bags(resident),
    }


@router.post("/collections", status_code=201)
async def start_collection(
    body: StartIn, resident: Resident, collections: Collections
) -> dict[str, Any]:
    try:
        return await collections.start(resident, body.qr)
    except SessionError as e:
        raise _http(e) from None


@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: uuid.UUID, resident: Resident, collections: Collections
) -> dict[str, Any]:
    try:
        return await collections.view(collection_id, resident)
    except SessionError as e:
        raise _http(e) from None


@router.post("/collections/{collection_id}/fills", status_code=201)
async def add_fill(
    collection_id: uuid.UUID, body: FillIn, resident: Resident, collections: Collections
) -> dict[str, Any]:
    try:
        return await collections.add_fill(collection_id, resident, body.bag)
    except SessionError as e:
        raise _http(e) from None


@router.post("/collections/{collection_id}/fills/{fill_id}/done")
async def finish_fill(
    collection_id: uuid.UUID, fill_id: uuid.UUID, resident: Resident, collections: Collections
) -> dict[str, Any]:
    try:
        return await collections.finish_fill(collection_id, fill_id, resident)
    except SessionError as e:
        raise _http(e) from None


@router.post("/collections/{collection_id}/finish")
async def finish_collection(
    collection_id: uuid.UUID, resident: Resident, collections: Collections
) -> dict[str, Any]:
    try:
        return await collections.finish(collection_id, resident)
    except SessionError as e:
        raise _http(e) from None


@router.post("/bags/{code}/seal")
async def seal_bag(code: str, resident: Resident, collections: Collections) -> dict[str, Any]:
    try:
        return await collections.seal_bag(code, resident)
    except SessionError as e:
        raise _http(e) from None


# ---------------------------------------------------------------- operator


class CollectorIn(BaseModel):
    """A participant, by the address of their account or of their phone key."""

    address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    name: str = Field(min_length=1, max_length=200)
    active: bool = True


class BagsIn(BaseModel):
    material: str
    count: int = Field(default=1, ge=1, le=200)


class ResolveIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


def incident_view(i: Incident) -> dict[str, Any]:
    return {
        "id": str(i.id),
        "kind": i.kind,
        "status": i.status,
        "container_id": i.container_id,
        "collection_id": str(i.collection_id) if i.collection_id else None,
        "bag_ids": [str(b) for b in i.bag_ids],
        "expected_g": i.expected_g,
        "measured_g": i.measured_g,
        "difference_g": i.measured_g - i.expected_g,
        "detail": i.detail,
        "created_at": i.created_at.isoformat(),
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
        "resolved_by": i.resolved_by,
        "resolution_note": i.resolution_note,
    }


@router.post("/operator/collectors", status_code=201)
async def name_collector(body: CollectorIn, _: Operator, request: Request) -> dict[str, Any]:
    address = body.address.lower()
    async with request.app.state.maker() as db:
        resident = await db.scalar(
            select(ResidentRow).where(
                or_(ResidentRow.address == address, ResidentRow.owner_address == address)
            )
        )
        if resident is None:
            raise HTTPException(
                404, {"code": "not_found", "detail": "no participant has signed in with that"}
            )
        collector = await db.get(Collector, resident.id)
        if collector is None:
            collector = Collector(resident_id=resident.id, name=body.name, active=body.active)
            db.add(collector)
        else:
            collector.name, collector.active = body.name, body.active
        await db.commit()
        return {
            "resident_id": str(resident.id),
            "address": resident.address,
            "name": collector.name,
            "active": collector.active,
        }


@router.get("/operator/collectors")
async def list_collectors(_: Operator, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        rows = await db.execute(
            select(Collector, ResidentRow)
            .join(ResidentRow, ResidentRow.id == Collector.resident_id)
            .order_by(Collector.name)
        )
        return [
            {
                "resident_id": str(c.resident_id),
                "address": r.address,
                "name": c.name,
                "active": c.active,
            }
            for c, r in rows
        ]


@router.post("/operator/bags", status_code=201)
async def create_bags(body: BagsIn, _: Operator, request: Request) -> list[dict[str, Any]]:
    """A batch of bags to print: each with its QR and material."""
    if body.material not in MATERIALS:
        raise HTTPException(422, f"unknown material {body.material!r}")
    for _attempt in range(3):  # a code collision is astronomically rare; retry anyway
        async with request.app.state.maker() as db:
            now = utcnow()
            bags = [
                Bag(
                    id=uuid.uuid4(),
                    code=new_bag_code(),
                    material=body.material,
                    status="open",
                    created_at=now,
                )
                for _ in range(body.count)
            ]
            db.add_all(bags)
            try:
                await db.commit()
            except IntegrityError:
                continue
            return [bag_view(b) for b in bags]
    raise HTTPException(503, "could not create bags; try again")


@router.get("/operator/bags")
async def list_bags(
    _: Operator,
    request: Request,
    status: Literal["open", "sealed", "sold", "settled"] | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        query = select(Bag, Collector.name).outerjoin(
            Collector, Collector.resident_id == Bag.collector_id
        )
        if status is not None:
            query = query.where(Bag.status == status)
        rows = await db.execute(query.order_by(Bag.created_at.desc()).limit(limit))
        return [{**bag_view(b), "collector": name} for b, name in rows]


@router.get("/operator/collections")
async def list_collections(
    _: Operator,
    request: Request,
    collections: Collections,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        rows = list(
            await db.execute(
                select(Collection.id, Collector.name)
                .outerjoin(Collector, Collector.resident_id == Collection.collector_id)
                .order_by(Collection.created_at.desc())
                .limit(limit)
            )
        )
    return [
        {**await collections.view(collection_id, None), "collector": name}
        for collection_id, name in rows
    ]


@router.get("/operator/incidents")
async def list_incidents(
    _: Operator,
    request: Request,
    status: Literal["open", "resolved"] | None = "open",
) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        query = select(Incident).order_by(Incident.created_at.desc()).limit(200)
        if status is not None:
            query = query.where(Incident.status == status)
        return [incident_view(i) for i in await db.scalars(query)]


@router.post("/operator/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: uuid.UUID, body: ResolveIn, operator: Operator, request: Request
) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        incident = await db.get(Incident, incident_id, with_for_update=True)
        if incident is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown incident"})
        if incident.status == "open":
            incident.status, incident.resolved_at = "resolved", utcnow()
            incident.resolved_by, incident.resolution_note = operator, body.note
            # Sales waiting on these bags try again now (docs/adr/0013).
            if incident.bag_ids:
                await db.execute(
                    update(SaleLine)
                    .where(SaleLine.status == "waiting", SaleLine.bag_id.in_(incident.bag_ids))
                    .values(next_attempt_at=utcnow())
                )
            await db.commit()
        return incident_view(incident)


@router.get("/operator/containers/balance")
async def containers_balance(_: Operator, request: Request) -> list[dict[str, Any]]:
    """Each container's latest collection and its open incidents, for the console."""
    async with request.app.state.maker() as db:
        open_incidents = dict(
            (
                await db.execute(
                    select(Incident.container_id, func.count(Incident.id))
                    .where(Incident.status == "open")
                    .group_by(Incident.container_id)
                )
            ).all()
        )
        containers = list(await db.scalars(select(Container).order_by(Container.id)))
        out = []
        for c in containers:
            last = await db.scalar(
                select(Collection)
                .where(Collection.container_id == c.id, Collection.state == "closed")
                .order_by(Collection.closed_at.desc())
                .limit(1)
            )
            out.append(
                {
                    "container_id": c.id,
                    "name": c.name,
                    "last_collection_at": last.closed_at.isoformat() if last else None,
                    "left_after_g": last.final_g if last else None,
                    "open_incidents": open_incidents.get(c.id, 0),
                }
            )
        return out
