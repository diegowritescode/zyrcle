"""Register the demo's simulated containers. Idempotent: safe to run on every deploy."""

import pathlib
import uuid

from sqlalchemy import select
from zyrcle_protocol import load_public_key

from .config import get_settings
from .db import make_engine, make_sessionmaker
from .models import Container, Device, MaterialPrice, Residence

RESIDENCE = "Conjunto demo Zyrcle"
CONTAINERS = {
    "ctr-0001": ("Contenedor PET y HDPE", ["pet", "hdpe"]),
    "ctr-0002": ("Contenedor de latas", ["metal"]),
    "ctr-0003": ("Contenedor de vidrio", ["glass"]),
    "ctr-0004": ("Contenedor de papel y cartón", ["paper", "cardboard"]),
}
# Reference prices for testnet demos only (COP/kg), not market data.
TEST_PRICES = {
    "pet": 1_000,
    "hdpe": 1_000,
    "metal": 4_000,
    "glass": 200,
    "paper": 400,
    "cardboard": 300,
}


async def seed(keys_dir: pathlib.Path, devices: list[str]) -> list[str]:
    engine = make_engine(get_settings().database_url)
    maker = make_sessionmaker(engine)
    done: list[str] = []
    async with maker() as db:
        residence = await db.scalar(select(Residence).where(Residence.name == RESIDENCE))
        if residence is None:
            residence = Residence(id=uuid.uuid4(), name=RESIDENCE)
            db.add(residence)
            done.append(f"residence {RESIDENCE}")
        for device_id in devices:
            pem = (keys_dir / f"{device_id}.pub.pem").read_text()
            load_public_key(pem)
            device = await db.get(Device, device_id)
            if device is None:
                db.add(Device(id=device_id, public_key_pem=pem))
                done.append(f"device {device_id}")
            elif device.public_key_pem != pem:
                device.public_key_pem = pem  # the simulator's key volume was recreated
                done.append(f"device {device_id} (new key)")
            if await db.get(Container, device_id) is None:
                name, materials = CONTAINERS.get(device_id, (f"Contenedor {device_id}", ["pet"]))
                db.add(
                    Container(
                        id=device_id,
                        residence_id=residence.id,
                        device_id=device_id,
                        name=name,
                        accepted_materials=materials,
                        area_mm2=250_000,
                        depth_mm=900,
                    )
                )
                done.append(f"container {device_id}")
        for material, price in TEST_PRICES.items():
            if await db.get(MaterialPrice, material) is None:
                db.add(MaterialPrice(material=material, cop_per_kg=price, source="manual"))
                done.append(f"price {material}")
        await db.commit()
    await engine.dispose()
    return done
