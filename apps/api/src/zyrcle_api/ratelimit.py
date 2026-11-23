"""Rate limits on the whole API (docs/adr/0035).

Every request takes a token from a bucket that refills steadily. Buckets are kept per class of
route and per caller:

- **emailed codes** (asking for one, using one, recovery, operator sign-in): strict, per IP
  address, so nobody can try codes or flood inboxes (each email also has its own limits);
- **phone sign-in** (nonce and signature): per IP address, generous, because a campus signs in
  through one address;
- **writes** (POST, PUT, PATCH, DELETE): per signed-in account, or per IP address without one;
- **reads**: the same, more lenient.

Signed-in callers are counted by their account, not their address, because a campus puts hundreds
of phones behind one public IP. A token only counts as an account if its signature checks;
anything else is counted by address, so inventing tokens buys nothing. The caller's address is the
last entry of `X-Forwarded-For` that our own proxy added (Traefik, one hop), never the first, which
the client can write. `/health`, CORS preflights and WebSockets are not limited.

The buckets live in the API process. One instance is enough for v1; several would need a shared
store.
"""

import json
import math
import secrets
import time
from collections.abc import Callable
from typing import Any

import jwt

from .config import Settings

SIGNIN_ROUTES = {("POST", "/v1/auth/nonce"), ("POST", "/v1/auth/verify")}
CODE_ROUTES = {
    ("POST", "/v1/me/email"),
    ("POST", "/v1/me/email/verify"),
    ("POST", "/v1/recovery/code"),
    ("POST", "/v1/recovery"),
    ("POST", "/v1/operator/login/code"),
    ("POST", "/v1/operator/login"),
}
WRITES = {"POST", "PUT", "PATCH", "DELETE"}
EXEMPT = {"/health"}


class Buckets:
    """Token buckets of `per_minute` requests a minute, refilled continuously."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._now = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._taken = 0

    def take(self, key: str, per_minute: int) -> float:
        """0 when allowed; otherwise the seconds until the next token."""
        now = self._now()
        tokens, last = self._buckets.get(key, (float(per_minute), now))
        tokens = min(float(per_minute), tokens + (now - last) * per_minute / 60)
        self._taken += 1
        if self._taken % 1_000 == 0:
            self._prune(now)
        if tokens >= 1:
            self._buckets[key] = (tokens - 1, now)
            return 0.0
        self._buckets[key] = (tokens, now)
        return (1 - tokens) * 60 / per_minute

    def _prune(self, now: float) -> None:
        stale = [k for k, (_, last) in self._buckets.items() if now - last > 600]
        for k in stale:
            del self._buckets[k]


def client_ip(scope: dict[str, Any], proxy_hops: int) -> str:
    """The address our proxy saw: `proxy_hops` entries from the right of X-Forwarded-For."""
    if proxy_hops > 0:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                hops = [h.strip() for h in value.decode("latin-1").split(",") if h.strip()]
                if len(hops) >= proxy_hops:
                    return hops[-proxy_hops]
    client = scope.get("client")
    return client[0] if client else "unknown"


def caller(scope: dict[str, Any], settings: Settings) -> str | None:
    """`role:subject` for a token whose signature checks, else None (counted by address)."""
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            text = value.decode("latin-1")
            if not text.lower().startswith("bearer "):
                return None
            token = text[7:].strip()
            if secrets.compare_digest(token, settings.operator_token):
                return "operator:token"
            try:
                claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            except jwt.PyJWTError:
                return None
            return f"{claims.get('role', 'unknown')}:{claims.get('sub', '')}"
    return None


class RateLimitMiddleware:
    """Pure ASGI, so WebSockets and streaming pass through untouched."""

    def __init__(self, app, settings: Settings, buckets: Buckets | None = None):
        self.app = app
        self.settings = settings
        self.buckets = buckets or Buckets()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or scope["path"] in EXEMPT:
            await self.app(scope, receive, send)
            return
        s = self.settings
        method, path = scope["method"], scope["path"].rstrip("/") or "/"
        ip = client_ip(scope, s.rate_limit_proxy_hops)
        if (method, path) in CODE_ROUTES:
            key, limit = f"codes:ip:{ip}", s.rate_limit_codes_per_min
        elif (method, path) in SIGNIN_ROUTES:
            key, limit = f"signin:ip:{ip}", s.rate_limit_signin_per_min
        else:
            who = caller(scope, s) or f"ip:{ip}"
            if method in WRITES:
                key, limit = f"write:{who}", s.rate_limit_write_per_min
            else:
                key, limit = f"read:{who}", s.rate_limit_read_per_min
        wait = self.buckets.take(key, limit)
        if wait <= 0:
            await self.app(scope, receive, send)
            return
        seconds = max(1, math.ceil(wait))
        body = json.dumps(
            {
                "detail": {
                    "code": "rate_limited",
                    "detail": f"too many requests; try again in {seconds} seconds",
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(seconds).encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
