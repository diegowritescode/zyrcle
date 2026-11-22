"""HTTP control panel for simulated containers (demo and tests only, never public).

    GET  /containers                       state of every container
    GET  /items                            the item catalog
    POST /containers/{id}/deposit          {"item": "pet_bottle", "count": 3}

In the real world nobody "deposits over HTTP": a person drops material into the bin. This panel
stands in for that person. The API's demo router is the only client, and it checks that the caller
owns the session first.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .container import CATALOG, LidClosed
from .runner import DeviceRunner


class DepositIn(BaseModel):
    item: str
    count: int = Field(default=1, ge=1, le=20)


def create_control_app(runners: dict[str, DeviceRunner]) -> FastAPI:
    app = FastAPI(title="Zyrcle simulator control", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "connected": [d for d, r in runners.items() if r.connected.is_set()]}

    @app.get("/items")
    def items() -> list[dict]:
        return [
            {"name": i.name, "weight_g": i.weight_g, "volume_ml": i.volume_ml, "label": i.label}
            for i in CATALOG.values()
        ]

    @app.get("/containers")
    def containers() -> list[dict]:
        return [
            {
                "device_id": device_id,
                "code": r.c.code,
                "lid_open": r.c.lid_open,
                "session_id": r.c.session.session_id if r.c.session else None,
                "connected": r.connected.is_set(),
            }
            for device_id, r in runners.items()
        ]

    @app.post("/containers/{device_id}/deposit")
    def deposit(device_id: str, body: DepositIn) -> dict:
        runner = runners.get(device_id)
        if runner is None:
            raise HTTPException(404, "unknown container")
        if body.item not in CATALOG:
            raise HTTPException(422, f"unknown item {body.item!r}")
        try:
            runner.c.deposit(body.item, body.count)
        except LidClosed:
            raise HTTPException(409, "the lid is closed") from None
        return {"ok": True, "session_id": runner.c.session.session_id if runner.c.session else None}

    return app
