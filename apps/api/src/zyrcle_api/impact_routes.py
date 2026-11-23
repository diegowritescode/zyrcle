"""Impact certificates (docs/adr/0027): operators issue them; anyone reads and verifies them."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import Operator
from .errors import SessionError
from .impact import ImpactService

router = APIRouter(prefix="/v1", tags=["impact"])


def impact_dep(request: Request) -> ImpactService:
    return request.app.state.impact


Impact = Annotated[ImpactService, Depends(impact_dep)]


def _http(e: SessionError) -> HTTPException:
    return HTTPException(e.status, {"code": e.code, "detail": e.detail})


class CertificateIn(BaseModel):
    host_id: uuid.UUID
    site_id: uuid.UUID | None = None
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="month, YYYY-MM")


@router.post("/operator/certificates/preview")
async def preview(body: CertificateIn, _: Operator, impact: Impact) -> dict[str, Any]:
    """What a certificate would hold right now, without claiming anything."""
    try:
        return await impact.preview(body.host_id, body.site_id, body.period)
    except SessionError as e:
        raise _http(e) from None


@router.post("/operator/certificates", status_code=201)
async def issue(body: CertificateIn, operator: Operator, impact: Impact) -> dict[str, Any]:
    try:
        return await impact.issue(body.host_id, body.site_id, body.period, operator)
    except SessionError as e:
        raise _http(e) from None


@router.get("/operator/certificates")
async def list_all(_: Operator, impact: Impact) -> list[dict[str, Any]]:
    return await impact.list()


@router.get("/hosts/{host_id}/certificates")
async def list_for_host(host_id: uuid.UUID, impact: Impact) -> list[dict[str, Any]]:
    """A host's certificates, newest month first. Public."""
    return await impact.list(host_id)


@router.get("/certificates/{certificate_id}")
async def get_certificate(certificate_id: uuid.UUID, impact: Impact) -> dict[str, Any]:
    """A certificate with its leaves, so anyone can recompute the root anchored on chain. Public."""
    try:
        return await impact.get(certificate_id)
    except SessionError as e:
        raise _http(e) from None
