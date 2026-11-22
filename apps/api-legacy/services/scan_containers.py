# Simulated container access (hackathon build). Replaced by the device protocol in phase 1.
from fastapi import HTTPException
from pydantic import BaseModel, Field

# Access code -> simulated container state. Container ids match the route containers.
contenedores_db = {
    "123456": {"id": 1, "peso_actual_g": 100_000},
    "654321": {"id": 2, "peso_actual_g": 120_000},
    "111111": {"id": 3, "peso_actual_g": 80_000},
    "999999": {"id": 4, "peso_actual_g": 60_000},
}

# Simulated deposit: every session adds 5 kg. Real weights come from the device in phase 1.
SIMULATED_DEPOSIT_G = 5_000


class CodigoRequest(BaseModel):
    codigo: str = Field(pattern=r"^\d{6}$")


class FinalizarRequest(BaseModel):
    codigo: str = Field(pattern=r"^\d{6}$")
    tiempoTranscurrido: float = Field(ge=0)


class ValidationResponse(BaseModel):
    message: str
    container_id: int


class FinalizeResponse(BaseModel):
    message: str
    container_id: int
    weight_grams: int


def _get(codigo: str) -> dict:
    contenedor = contenedores_db.get(codigo)
    if not contenedor:
        raise HTTPException(status_code=400, detail="Código no válido")
    return contenedor


def validar_codigo(codigo: str) -> ValidationResponse:
    contenedor = _get(codigo)
    return ValidationResponse(message="Acceso permitido", container_id=contenedor["id"])


def finalizar(codigo: str, tiempo_transcurrido: float) -> FinalizeResponse:
    contenedor = _get(codigo)
    contenedor["peso_actual_g"] += SIMULATED_DEPOSIT_G
    minutos = tiempo_transcurrido / 60
    message = (
        f"Reciclaje completado en {minutos:.2f} minutos. "
        f"Reciclaje añadido: {SIMULATED_DEPOSIT_G / 1000:g} kg."
    )
    return FinalizeResponse(
        message=message, container_id=contenedor["id"], weight_grams=SIMULATED_DEPOSIT_G
    )
