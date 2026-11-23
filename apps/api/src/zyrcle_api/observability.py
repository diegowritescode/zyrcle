"""Error reports to Sentry (docs/adr/0033), with no personal data in them.

Unhandled errors in requests and every `log.exception` (the workers log their failures that way)
become reports with the code's context. Before a report leaves, `scrub` replaces what could name a
person or open a wallet: email addresses, long hex strings (private keys, signatures), bearer
tokens and JWTs, and it drops request bodies, cookies and headers. Account addresses (40 hex) stay:
they are public on the chain and are what an operator needs to find a stuck payment.
"""

import re
from typing import Any

from .config import Settings

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LONG_HEX = re.compile(r"\b(?:0x)?[0-9a-fA-F]{64,}\b")
BEARER = re.compile(r"(?i)bearer\s+[\w.~+/=-]+")
JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")
REDACTED = "[redacted]"


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        for pattern in (BEARER, JWT, EMAIL, LONG_HEX):
            value = pattern.sub(REDACTED, value)
        return value
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def scrub(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sentry's `before_send`: remove personal data and secrets from a report."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "headers", "env"):
            request.pop(key, None)
        if "query_string" in request:
            request["query_string"] = REDACTED
    event.pop("user", None)
    return _clean(event)


def start_error_reports(settings: Settings) -> bool:
    """Start Sentry when a DSN is set. Returns whether it started."""
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        release=settings.release,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=scrub,  # type: ignore[arg-type]
        max_request_body_size="never",
    )
    return True
