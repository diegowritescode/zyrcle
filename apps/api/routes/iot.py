import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from models.iot import Container
from services import iot_service

router = APIRouter()


@router.post("/contenedores")
def receive_containers(data: list[Container], x_device_token: Annotated[str, Header()] = ""):
    """Replace the container snapshot. Only callers holding IOT_INGEST_TOKEN may write."""
    expected = os.getenv("IOT_INGEST_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="IoT ingest is not configured.")
    if not hmac.compare_digest(x_device_token, expected):
        raise HTTPException(status_code=401, detail="Invalid device token.")
    iot_service.store_containers([d.model_dump() for d in data])
    return {"message": f"{len(data)} containers stored successfully."}
