"""Rate limits (docs/adr/0035): per IP for sign-in and codes, per account otherwise."""

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from zyrcle_api.ratelimit import Buckets, RateLimitMiddleware, client_ip


class Clock:
    def __init__(self) -> None:
        self.t = 1_000.0

    def __call__(self) -> float:
        return self.t


def test_a_bucket_refills_steadily():
    clock = Clock()
    b = Buckets(clock)
    assert all(b.take("k", 3) == 0 for _ in range(3))
    assert b.take("k", 3) == pytest.approx(20)  # 3 a minute: one every 20 s
    clock.t += 20
    assert b.take("k", 3) == 0
    assert b.take("other", 3) == 0  # every key has its own bucket


def test_the_address_is_the_one_our_proxy_saw_not_what_the_client_wrote():
    scope = {"client": ("10.0.0.5", 1), "headers": [(b"x-forwarded-for", b"6.6.6.6, 190.1.2.3")]}
    assert client_ip(scope, 1) == "190.1.2.3"
    assert client_ip(scope, 0) == "10.0.0.5"
    assert client_ip({"client": ("10.0.0.5", 1), "headers": []}, 1) == "10.0.0.5"


@pytest.fixture
def limited(settings):
    s = settings.model_copy(
        update={
            "rate_limits_enabled": True,
            "rate_limit_codes_per_min": 2,
            "rate_limit_signin_per_min": 5,
            "rate_limit_write_per_min": 3,
            "rate_limit_read_per_min": 4,
        }
    )
    api = FastAPI()

    @api.get("/v1/things")
    async def read():
        return {"ok": True}

    @api.post("/v1/things")
    async def write():
        return {"ok": True}

    @api.post("/v1/auth/nonce")
    async def nonce():
        return {"ok": True}

    @api.post("/v1/operator/login/code")
    async def code():
        return {"ok": True}

    @api.get("/health")
    async def health():
        return {"ok": True}

    api.add_middleware(RateLimitMiddleware, settings=s, buckets=Buckets(Clock()))
    return s, AsyncClient(transport=ASGITransport(app=api), base_url="http://t")


def resident(s, sub: str) -> dict:
    token = jwt.encode({"sub": sub, "role": "resident"}, s.jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def test_reads_writes_and_sign_ins_have_their_own_limits(limited):
    s, client = limited
    async with client:
        reads = [(await client.get("/v1/things")).status_code for _ in range(5)]
        writes = [(await client.post("/v1/things")).status_code for _ in range(4)]
        assert reads == [200] * 4 + [429] and writes == [200] * 3 + [429]
        codes = [(await client.post("/v1/operator/login/code")).status_code for _ in range(3)]
        signins = [(await client.post("/v1/auth/nonce")).status_code for _ in range(6)]
        assert codes == [200, 200, 429] and signins == [200] * 5 + [429]
        r = await client.post("/v1/operator/login/code")
        assert r.json()["detail"]["code"] == "rate_limited"
        assert int(r.headers["retry-after"]) >= 1
        assert (await client.get("/health")).status_code == 200  # never limited


async def test_signed_in_people_behind_one_campus_address_are_counted_apart(limited):
    s, client = limited
    async with client:
        for who in ("ana", "beto", "caro"):
            for _ in range(4):
                assert (await client.get("/v1/things", headers=resident(s, who))).status_code == 200
        assert (await client.get("/v1/things", headers=resident(s, "ana"))).status_code == 429


async def test_made_up_tokens_count_as_the_same_address(limited):
    s, client = limited
    async with client:
        codes = []
        for i in range(5):
            r = await client.get("/v1/things", headers={"Authorization": f"Bearer fake-{i}"})
            codes.append(r.status_code)
        assert codes == [200] * 4 + [429]


async def test_the_real_app_answers_429_with_cors_headers(settings):
    from asgi_lifespan import LifespanManager

    from zyrcle_api.main import create_app

    s = settings.model_copy(
        update={
            "rate_limits_enabled": True,
            "rate_limit_read_per_min": 1,
            "cors_origins": "https://w",
        }
    )
    app = create_app(s)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            first = await client.get("/v1/stats", headers={"Origin": "https://w"})
            second = await client.get("/v1/stats", headers={"Origin": "https://w"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["access-control-allow-origin"] == "https://w"
