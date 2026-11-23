"""Helpers for tests that empty containers into bags (docs/adr/0012)."""

from .helpers import OPS, headers, qr, wait_for


async def bags(client, material: str, count: int = 1) -> list[dict]:
    r = await client.post(
        "/v1/operator/bags", headers=OPS, json={"material": material, "count": count}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def collection(client, person, collection_id: str) -> dict:
    r = await client.get(f"/v1/collections/{collection_id}", headers=headers(person))
    assert r.status_code == 200, r.text
    return r.json()


async def wait_collection(client, person, collection_id: str, check, timeout=8.0) -> dict:
    holder: dict = {}

    async def ok() -> bool:
        holder["c"] = await collection(client, person, collection_id)
        return check(holder["c"])

    await wait_for(ok, timeout)
    return holder["c"]


async def take(client, person, c: dict, bag: dict | None, kind: str | None) -> dict:
    """Scan `bag` (None: residue), take `kind` out of the container, wait for the scale, done."""
    r = await client.post(
        f"/v1/collections/{c['id']}/fills",
        headers=headers(person),
        json={"bag": bag["qr"] if bag else None},
    )
    assert r.status_code == 201, r.text
    fill_id = r.json()["open_fill_id"]
    before = r.json()["weight_g"]
    r = await client.post(
        f"/v1/demo/collections/{c['id']}/take-out", headers=headers(person), json={"kind": kind}
    )
    assert r.status_code == 200, r.text
    taken = r.json()["grams"]
    if taken:
        await wait_collection(
            client, person, c["id"], lambda x: x["weight_g"] <= before - taken + 10
        )
    r = await client.post(
        f"/v1/collections/{c['id']}/fills/{fill_id}/done", headers=headers(person)
    )
    assert r.status_code == 200, r.text
    return next(f for f in r.json()["fills"] if f["id"] == fill_id)


async def open_collection(client, person, runner) -> dict:
    r = await client.post("/v1/collections", headers=headers(person), json={"qr": qr(runner)})
    assert r.status_code == 201, r.text
    return await wait_collection(
        client, person, r.json()["id"], lambda x: x["state"] == "open" and x["weight_g"]
    )


async def incidents(client, collection_id: str) -> list[dict]:
    r = await client.get("/v1/operator/incidents?status=open", headers=OPS)
    return [i for i in r.json() if i["collection_id"] == collection_id]
