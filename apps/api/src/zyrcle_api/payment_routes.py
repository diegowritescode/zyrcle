"""Paying merchants and redeeming ZYR (docs/adr/0029): participants, merchants and operators."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from .chain import load_account_file
from .deps import Operator, Resident
from .errors import SessionError
from .models import Host, Merchant, RedemptionRequest, Site
from .models import Resident as ResidentRow
from .payments import PaymentService, redemption_view

router = APIRouter(prefix="/v1", tags=["payments"])


def payments_dep(request: Request) -> PaymentService:
    return request.app.state.payments


Payments = Annotated[PaymentService, Depends(payments_dep)]


def _http(e: SessionError) -> HTTPException:
    return HTTPException(e.status, {"code": e.code, "detail": e.detail})


class ChargeIn(BaseModel):
    amount_cop: int = Field(gt=0, le=1_000_000)
    concept: str = Field(default="", max_length=120)


class SignedIn(BaseModel):
    signature: str = Field(pattern=r"^0x[0-9a-fA-F]{130}$")
    deadline: int = Field(gt=0)
    nonce: int = Field(ge=0)


class RedeemIn(BaseModel):
    amount_cop: int = Field(gt=0, le=100_000_000)


# ---------------------------------------------------------------- participants


@router.get("/payments/{payment_id}")
async def get_payment(payment_id: uuid.UUID, _: Resident, payments: Payments) -> dict[str, Any]:
    try:
        return await payments.get(payment_id)
    except SessionError as e:
        raise _http(e) from None


@router.post("/payments/{payment_id}/intent")
async def payment_intent(
    payment_id: uuid.UUID, resident: Resident, payments: Payments
) -> dict[str, Any]:
    """The EIP-712 message the payer's phone signs: one transfer from their account."""
    try:
        return await payments.payment_intent(payment_id, resident)
    except SessionError as e:
        raise _http(e) from None


@router.post("/payments/{payment_id}/pay")
async def pay(
    payment_id: uuid.UUID, body: SignedIn, resident: Resident, payments: Payments
) -> dict[str, Any]:
    try:
        return await payments.pay(payment_id, resident, body.signature, body.deadline, body.nonce)
    except SessionError as e:
        raise _http(e) from None


# ---------------------------------------------------------------- merchants


@router.get("/merchant")
async def merchant_home(resident: Resident, payments: Payments) -> dict[str, Any]:
    try:
        return await payments.merchant_home(resident)
    except SessionError as e:
        raise _http(e) from None


@router.post("/merchant/charges", status_code=201)
async def charge(body: ChargeIn, resident: Resident, payments: Payments) -> dict[str, Any]:
    try:
        return await payments.charge(resident, body.amount_cop, body.concept)
    except SessionError as e:
        raise _http(e) from None


@router.post("/merchant/redemptions", status_code=201)
async def redemption_intent(
    body: RedeemIn, resident: Resident, payments: Payments
) -> dict[str, Any]:
    try:
        return await payments.redemption_intent(resident, body.amount_cop)
    except SessionError as e:
        raise _http(e) from None


@router.post("/merchant/redemptions/{redemption_id}/sign")
async def sign_redemption(
    redemption_id: uuid.UUID, body: SignedIn, resident: Resident, payments: Payments
) -> dict[str, Any]:
    try:
        return await payments.sign_redemption(
            redemption_id, resident, body.signature, body.deadline, body.nonce
        )
    except SessionError as e:
        raise _http(e) from None


# ---------------------------------------------------------------- operator


class MerchantIn(BaseModel):
    address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    name: str = Field(min_length=1, max_length=200)
    nit: str = Field(min_length=3, max_length=32, description="tax id, the KYC reference")
    host_id: uuid.UUID | None = None
    active: bool = True
    # Where participants find it (docs/adr/0041); shown publicly.
    site_id: uuid.UUID | None = None
    place: str | None = Field(default=None, max_length=200)
    hours: str | None = Field(default=None, max_length=120)
    offer: str | None = Field(default=None, max_length=300)


class SettleIn(BaseModel):
    bank_ref: str = Field(min_length=1, max_length=100)


def _text(value: str | None) -> str | None:
    return (value or "").strip() or None


def merchant_view(m: Merchant, r: ResidentRow) -> dict[str, Any]:
    return {
        "resident_id": str(m.resident_id),
        "address": r.address,
        "name": m.name,
        "nit": m.nit,
        "host_id": str(m.host_id) if m.host_id else None,
        "active": m.active,
        "site_id": str(m.site_id) if m.site_id else None,
        "place": m.place,
        "hours": m.hours,
        "offer": m.offer,
    }


@router.post("/operator/merchants", status_code=201)
async def name_merchant(body: MerchantIn, _: Operator, request: Request) -> dict[str, Any]:
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
        if body.host_id is not None and await db.get(Host, body.host_id) is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown host"})
        if body.site_id is not None:
            site = await db.get(Site, body.site_id)
            if site is None or site.host_id != body.host_id:
                raise HTTPException(
                    422,
                    {"code": "invalid", "detail": "the site must belong to the merchant's host"},
                )
        m = await db.get(Merchant, resident.id)
        if m is None:
            m = Merchant(resident_id=resident.id, name=body.name, nit=body.nit)
            db.add(m)
        m.name, m.nit, m.host_id, m.active = body.name, body.nit, body.host_id, body.active
        m.site_id, m.place = body.site_id, _text(body.place)
        m.hours, m.offer = _text(body.hours), _text(body.offer)
        await db.commit()
        return merchant_view(m, resident)


@router.get("/operator/merchants")
async def list_merchants(_: Operator, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        rows = await db.execute(
            select(Merchant, ResidentRow)
            .join(ResidentRow, ResidentRow.id == Merchant.resident_id)
            .order_by(Merchant.name)
        )
        return [merchant_view(m, r) for m, r in rows]


@router.get("/merchants")
async def where_to_spend(request: Request) -> list[dict[str, Any]]:
    """Public: the active merchants of each host, where to find them and what they sell
    (docs/adr/0041). Never the tax id or the account."""
    async with request.app.state.maker() as db:
        rows = await db.execute(
            select(Merchant, Host, Site)
            .join(Host, Host.id == Merchant.host_id)
            .outerjoin(Site, Site.id == Merchant.site_id)
            .where(Merchant.active.is_(True))
            .order_by(Host.name, Site.name.nulls_last(), Merchant.name)
        )
        return [
            {
                "name": m.name,
                "host": {"id": str(h.id), "name": h.name},
                "site": {"id": str(s.id), "name": s.name} if s is not None else None,
                "place": m.place,
                "hours": m.hours,
                "offer": m.offer,
            }
            for m, h, s in rows
        ]


@router.get("/operator/redemptions")
async def list_redemptions(
    _: Operator,
    request: Request,
    status: Literal["requested", "pending", "settled", "refunded", "failed"] | None = None,
) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        query = (
            select(RedemptionRequest, Merchant)
            .join(Merchant, Merchant.resident_id == RedemptionRequest.merchant_id)
            .where(RedemptionRequest.status != "signing")
            .order_by(RedemptionRequest.created_at.desc())
            .limit(100)
        )
        if status is not None:
            query = query.where(RedemptionRequest.status == status)
        return [
            {**redemption_view(r), "merchant": m.name, "nit": m.nit}
            for r, m in await db.execute(query)
        ]


def _operator_key(request: Request):
    settings = request.app.state.settings
    if not settings.sales_enabled:
        raise HTTPException(503, {"code": "unavailable", "detail": "no Treasury operator key"})
    return load_account_file(settings.operator_key_file)


@router.post("/operator/redemptions/{redemption_id}/settle")
async def settle(
    redemption_id: uuid.UUID,
    body: SettleIn,
    operator: Operator,
    request: Request,
    payments: Payments,
) -> dict[str, Any]:
    """The pesos were transferred to the merchant: retire the ZYR and lower the backing."""
    try:
        return await payments.decide_redemption(
            redemption_id, True, body.bank_ref, operator, _operator_key(request)
        )
    except SessionError as e:
        raise _http(e) from None


@router.post("/operator/redemptions/{redemption_id}/refund")
async def refund(
    redemption_id: uuid.UUID, operator: Operator, request: Request, payments: Payments
) -> dict[str, Any]:
    try:
        return await payments.decide_redemption(
            redemption_id, False, None, operator, _operator_key(request)
        )
    except SessionError as e:
        raise _http(e) from None
