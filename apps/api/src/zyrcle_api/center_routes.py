"""Operator routes for collection centers and their prices (docs/adr/0037)."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .centers import center_view, suggested_prices
from .deps import Operator
from .models import CenterPrice, CollectionCenter, Site
from .sessions import MATERIALS, utcnow

router = APIRouter(prefix="/v1/operator", tags=["collection centers"])


class CenterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=300)
    contact: str | None = Field(default=None, max_length=200)


class CenterPriceIn(BaseModel):
    cop_per_kg: int = Field(ge=0, le=1_000_000)
    source: Literal["manual", "sales"] = "manual"


class SiteCenterIn(BaseModel):
    center_id: uuid.UUID | None


@router.get("/centers")
async def list_centers(_: Operator, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        centers = await db.scalars(select(CollectionCenter).order_by(CollectionCenter.name))
        return [await center_view(db, c) for c in centers]


@router.post("/centers", status_code=201)
async def create_center(body: CenterIn, _: Operator, request: Request) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        center = CollectionCenter(id=uuid.uuid4(), **body.model_dump())
        db.add(center)
        try:
            await db.commit()
        except IntegrityError:
            raise HTTPException(
                409, {"code": "conflict", "detail": "a center with that name exists"}
            ) from None
        return await center_view(db, center)


@router.put("/centers/{center_id}/prices/{material}")
async def set_center_price(
    center_id: uuid.UUID, material: str, body: CenterPriceIn, who: Operator, request: Request
) -> dict[str, Any]:
    if material not in MATERIALS:
        raise HTTPException(422, {"code": "invalid", "detail": f"unknown material {material!r}"})
    async with request.app.state.maker() as db:
        center = await db.get(CollectionCenter, center_id)
        if center is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown center"})
        price = await db.get(CenterPrice, (center_id, material))
        if price is None:
            price = CenterPrice(center_id=center_id, material=material)
            db.add(price)
        price.cop_per_kg, price.source = body.cop_per_kg, body.source
        price.updated_by, price.updated_at = who, utcnow()
        await db.commit()
        return await center_view(db, center)


@router.get("/centers/{center_id}/suggested-prices")
async def center_suggestions(
    center_id: uuid.UUID, _: Operator, request: Request
) -> dict[str, dict[str, int]]:
    async with request.app.state.maker() as db:
        if await db.get(CollectionCenter, center_id) is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown center"})
        return await suggested_prices(db, center_id, utcnow())


@router.put("/sites/{site_id}/center")
async def set_site_center(
    site_id: uuid.UUID, body: SiteCenterIn, _: Operator, request: Request
) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        site = await db.get(Site, site_id)
        if site is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown site"})
        if body.center_id is not None and await db.get(CollectionCenter, body.center_id) is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown center"})
        site.center_id = body.center_id
        await db.commit()
        center = str(site.center_id) if site.center_id else None
        return {"site_id": str(site.id), "center_id": center}
