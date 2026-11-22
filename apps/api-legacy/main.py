import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import evidence, iot, residencia, rutas, scan, stats, status
from services import iot_service

# Comma-separated list of allowed browser origins, e.g.
# CORS_ORIGINS="https://zyrcle.deviego.xyz,http://localhost:8080"
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",") if o.strip()
]

app = FastAPI(title="Zyrcle API (hackathon build)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load containers on startup
iot_service.load_from_disk()

app.include_router(iot.router, prefix="/api/iot", tags=["IoT"])
app.include_router(rutas.router, prefix="/api", tags=["Rutas"])
app.include_router(stats.router, prefix="/api/stats", tags=["Stats"])
app.include_router(residencia.router, prefix="/api/residencia", tags=["Residencia"])
app.include_router(status.router, prefix="/api", tags=["Status"])
app.include_router(scan.router, prefix="/api", tags=["Scan"])
app.include_router(evidence.router, prefix="/api", tags=["Evidence"])
