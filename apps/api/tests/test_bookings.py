"""Time slots: booking an hour, its rules, and what a full or closed hour does to a deposit."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from .helpers import OPS, headers, qr, sign_in, wait_state

pytestmark = pytest.mark.integration


def _tz(settings) -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def _at(settings, days: int, hour: int, minute: int = 0) -> datetime:
    tz = _tz(settings)
    day = datetime.now(tz).date() + timedelta(days=days)
    return datetime.combine(day, time(hour, minute), tzinfo=tz)


async def _site(client) -> dict:
    return next(r for r in (await client.get("/v1/sites")).json() if r["name"] == "Torres del Río")


async def _schedule(client, site_id: str, **schedule) -> None:
    r = await client.put(f"/v1/operator/sites/{site_id}/schedule", json=schedule, headers=OPS)
    assert r.status_code == 200, r.text


async def _book(client, resident, container_id: str, starts_at: datetime):
    return await client.post(
        "/v1/bookings",
        json={"container_id": container_id, "starts_at": starts_at.isoformat()},
        headers=headers(resident),
    )


async def _slot(client, resident, container_id: str, day: str, hour: int) -> dict:
    r = await client.get(
        f"/v1/containers/{container_id}/slots?day={day}", headers=headers(resident)
    )
    assert r.status_code == 200, r.text
    return next(s for s in r.json()["slots"] if s["hour"] == hour)


async def test_a_resident_books_an_hour_and_cancels_it(client, devices, resident, settings):
    listed = (await client.get("/v1/containers")).json()
    assert {"ctr-0001", "ctr-0002", "ctr-0003"} <= {c["id"] for c in listed}
    assert all("code" not in str(c).lower() for c in listed)

    starts = _at(settings, 1, 10)
    day = starts.date().isoformat()
    r = await client.get(f"/v1/containers/ctr-0001/slots?day={day}", headers=headers(resident))
    body = r.json()
    assert len(body["days"]) == 7 and body["day"] == day and len(body["slots"]) == 24
    before = await _slot(client, resident, "ctr-0001", day, 10)
    assert before["available"] and not before["mine"] and before["state"] == "future"

    r = await _book(client, resident, "ctr-0001", starts)
    assert r.status_code == 201, r.text
    booking = r.json()
    assert booking["state"] == "upcoming" and booking["hour"] == 10 and booking["day"] == day
    assert booking["container_name"] == "Contenedor ctr-0001"

    after = await _slot(client, resident, "ctr-0001", day, 10)
    assert after["mine"] and after["taken"] == before["taken"] + 1 and not after["available"]
    mine = (await client.get("/v1/bookings", headers=headers(resident))).json()
    assert [b["id"] for b in mine] == [booking["id"]]

    again = await _book(client, resident, "ctr-0001", starts)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_booked"

    r = await client.delete(f"/v1/bookings/{booking['id']}", headers=headers(resident))
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert (await client.get("/v1/bookings", headers=headers(resident))).json() == []
    assert (await _slot(client, resident, "ctr-0001", day, 10))["taken"] == before["taken"]


async def test_booking_rules(client, devices, resident, settings):
    async def code(starts_at, container="ctr-0001") -> tuple[int, str | None]:
        r = await _book(client, resident, container, starts_at)
        detail = r.json().get("detail")
        return r.status_code, detail.get("code") if isinstance(detail, dict) else None

    assert await code(_at(settings, 1, 10, 30)) == (422, "invalid")  # not on the hour
    assert await code(_at(settings, -1, 10)) == (422, "invalid")  # over
    assert await code(_at(settings, 7, 10)) == (422, "invalid")  # beyond the 7 bookable days
    assert await code(_at(settings, 1, 10), "ctr-9999") == (404, "not_found")
    naive = await client.post(
        "/v1/bookings",
        json={"container_id": "ctr-0001", "starts_at": "2030-01-01T10:00:00"},
        headers=headers(resident),
    )
    assert naive.status_code == 422

    made = []
    for hour in (8, 9, 10):
        r = await _book(client, resident, "ctr-0002", _at(settings, 2, hour))
        assert r.status_code == 201, r.text
        made.append(r.json()["id"])
    assert await code(_at(settings, 2, 11), "ctr-0002") == (409, "too_many_bookings")
    for booking_id in made:
        await client.delete(f"/v1/bookings/{booking_id}", headers=headers(resident))
    assert (await _book(client, resident, "ctr-0002", _at(settings, 2, 11))).status_code == 201


async def test_a_full_hour_opens_only_for_residents_with_a_spot(
    client, devices, resident, settings
):
    site = await _site(client)
    tz = _tz(settings)
    now = datetime.now(tz)
    day, hour = now.date().isoformat(), now.hour
    current = await _slot(client, resident, "ctr-0003", day, hour)
    assert current["state"] == "now"
    try:
        # Leave exactly one free spot in this hour, and give it to `resident`.
        await _schedule(client, site["id"], slot_capacity=current["taken"] + 1)
        r = await _book(client, resident, "ctr-0003", datetime.fromisoformat(current["starts_at"]))
        assert r.status_code == 201, r.text
        assert r.json()["state"] == "now"

        walk_in = await sign_in(client, settings)
        r = await client.post(
            "/v1/sessions",
            json={"qr": qr(devices["ctr-0003"]), "material": "glass"},
            headers=headers(walk_in),
        )
        assert r.status_code == 409 and r.json()["detail"]["code"] == "slot_full"

        r = await client.post(
            "/v1/sessions",
            json={"qr": qr(devices["ctr-0003"]), "material": "glass"},
            headers=headers(resident),
        )
        assert r.status_code == 201, r.text
        session = r.json()
        await wait_state(client, resident, session["id"], "open")
        await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
        await wait_state(client, resident, session["id"], "empty", "verified", "review")

        mine = (await client.get("/v1/bookings", headers=headers(resident))).json()
        assert [b["state"] for b in mine] == ["used"]
        r = await client.delete(f"/v1/bookings/{mine[0]['id']}", headers=headers(resident))
        assert r.status_code == 403
    finally:
        await _schedule(client, site["id"], slot_capacity=1000)


async def test_a_closed_hour_refuses_deposits_and_bookings(client, devices, resident, settings):
    site = await _site(client)
    now = datetime.now(_tz(settings))
    hours = (
        {"opens_hour": now.hour + 1, "closes_hour": 24}
        if now.hour < 23
        else {
            "opens_hour": 0,
            "closes_hour": 23,
        }
    )
    bad = await client.put(
        f"/v1/operator/sites/{site['id']}/schedule",
        json={"opens_hour": 10, "closes_hour": 10},
        headers=OPS,
    )
    assert bad.status_code == 422
    try:
        await _schedule(client, site["id"], slot_capacity=1000, **hours)
        r = await client.post(
            "/v1/sessions",
            json={"qr": qr(devices["ctr-0001"]), "material": "pet"},
            headers=headers(resident),
        )
        assert r.status_code == 409 and r.json()["detail"]["code"] == "closed"
        assert f"{hours['opens_hour']:02d}:00" in r.json()["detail"]["detail"]

        r = await _book(
            client, resident, "ctr-0001", now.replace(minute=0, second=0, microsecond=0)
        )
        assert r.status_code == 409 and r.json()["detail"]["code"] == "closed"
        day = await client.get(
            f"/v1/containers/ctr-0001/slots?day={now.date().isoformat()}",
            headers=headers(resident),
        )
        assert [s["hour"] for s in day.json()["slots"]] == list(
            range(hours["opens_hour"], hours["closes_hour"])
        )
    finally:
        await _schedule(client, site["id"], slot_capacity=1000)
