"""Register the demo's host, sites and simulated containers. Idempotent: safe to run on every
deploy.

The demo is a university with two campuses (docs/adr/0011). Older deployments had one residence,
"Conjunto demo Zyrcle", holding every container; the seed renames it into the first campus and
moves the containers where the layout below puts them, so earlier demo deposits are kept."""

import pathlib
import uuid

from sqlalchemy import select
from zyrcle_protocol import load_public_key

from .config import get_settings
from .db import make_engine, make_sessionmaker
from .models import Container, Device, Host, MaterialPrice, Site

HOST = "Universidad Demo Zyrcle"
LEGACY_SITE = "Conjunto demo Zyrcle"  # the single residence of deployments before ADR 0011
SITES = ("Campus Norte", "Campus Centro")
# container id -> (name, accepted materials, campus)
CONTAINERS = {
    "ctr-0001": ("Contenedor PET y HDPE", ["pet", "hdpe"], "Campus Norte"),
    "ctr-0002": ("Contenedor de latas", ["metal"], "Campus Norte"),
    "ctr-0003": ("Contenedor de vidrio", ["glass"], "Campus Centro"),
    "ctr-0004": ("Contenedor de papel y cartón", ["paper", "cardboard"], "Campus Centro"),
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
        sites = await _demo_sites(db, done)
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
            name, materials, campus = CONTAINERS.get(
                device_id, (f"Contenedor {device_id}", ["pet"], SITES[0])
            )
            container = await db.get(Container, device_id)
            if container is None:
                db.add(
                    Container(
                        id=device_id,
                        site_id=sites[campus].id,
                        device_id=device_id,
                        name=name,
                        accepted_materials=materials,
                        area_mm2=250_000,
                        depth_mm=900,
                    )
                )
                done.append(f"container {device_id}")
            elif container.site_id != sites[campus].id:
                container.site_id = sites[campus].id
                done.append(f"container {device_id} moved to {campus}")
        for material, price in TEST_PRICES.items():
            if await db.get(MaterialPrice, material) is None:
                db.add(MaterialPrice(material=material, cop_per_kg=price, source="manual"))
                done.append(f"price {material}")
        await db.commit()
    await engine.dispose()
    return done


async def _demo_sites(db, done: list[str]) -> dict[str, Site]:
    """The demo host and its campuses, created or renamed from the legacy residence."""
    host = await db.scalar(select(Host).where(Host.name == HOST))
    legacy = await db.scalar(select(Site).where(Site.name == LEGACY_SITE))
    if host is None and legacy is not None:
        # The migration gave the legacy residence a host of its own, with the same name.
        host = await db.get(Host, legacy.host_id)
        assert host is not None
        host.name, host.kind = HOST, "university"
        done.append(f"host {LEGACY_SITE} renamed to {HOST}")
    if host is None:
        host = Host(id=uuid.uuid4(), name=HOST, kind="university")
        db.add(host)
        await db.flush()
        done.append(f"host {HOST}")
    sites: dict[str, Site] = {}
    for name in SITES:
        site = await db.scalar(select(Site).where(Site.host_id == host.id, Site.name == name))
        if site is None and legacy is not None and legacy.host_id == host.id:
            site, legacy = legacy, None
            done.append(f"site {LEGACY_SITE} renamed to {name}")
            site.name = name
        if site is None:
            site = Site(id=uuid.uuid4(), host_id=host.id, name=name)
            db.add(site)
            done.append(f"site {name}")
        sites[name] = site
    await db.flush()
    return sites
