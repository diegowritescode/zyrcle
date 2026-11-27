"""Impact certificates (docs/adr/0027): operators issue them; anyone reads and verifies them, and
downloads them as a PDF (docs/adr/0046)."""

import uuid
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .certificate_pdf import pdf_filename, render_certificate
from .deps import Operator
from .errors import SessionError
from .impact import ImpactService, utcnow

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


@router.get("/certificates/{certificate_id}/pdf")
async def certificate_pdf(certificate_id: uuid.UUID, request: Request, impact: Impact) -> Response:
    """The certificate as a formal PDF with a QR to its verification page (docs/adr/0046), the
    same one the monthly report emails. Public, like the certificate."""
    try:
        view = await impact.get(certificate_id, with_leaves=False)
    except SessionError as e:
        raise _http(e) from None
    settings = request.app.state.settings
    pdf = render_certificate(
        view, settings.public_web_url, settings.chain_id, ZoneInfo(settings.timezone), utcnow()
    )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{pdf_filename(view)}"'},
    )
