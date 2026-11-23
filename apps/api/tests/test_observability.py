"""Error reports carry no personal data or secrets (docs/adr/0033)."""

from zyrcle_api.observability import REDACTED, scrub, start_error_reports


def test_reports_lose_emails_keys_tokens_and_request_bodies():
    key = "0x" + "ab" * 32
    account = "0x" + "12" * 20
    event = {
        "message": f"payout to {account} failed for diego@example.com with key {key}",
        "request": {
            "url": "https://api/v1/me",
            "data": {"email": "diego@example.com"},
            "headers": {"Authorization": "Bearer abc.def.ghi"},
            "cookies": {"s": "1"},
            "query_string": "email=diego@example.com",
        },
        "user": {"email": "diego@example.com"},
        "extra": {"token": "eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl", "list": ["Bearer xyz", 3]},
    }
    clean = scrub(event)
    assert clean["message"] == f"payout to {account} failed for {REDACTED} with key {REDACTED}"
    assert set(clean["request"]) == {"url", "query_string"}
    assert clean["request"]["query_string"] == REDACTED
    assert "user" not in clean
    assert clean["extra"] == {"token": REDACTED, "list": [REDACTED, 3]}


def test_no_dsn_no_reports(settings):
    assert start_error_reports(settings.model_copy(update={"sentry_dsn": None})) is False


def test_a_dsn_starts_reports_that_pass_through_scrub(settings, monkeypatch):
    import sentry_sdk

    seen = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    on = settings.model_copy(
        update={"sentry_dsn": "https://k@o1.ingest.sentry.io/1", "release": "abc"}
    )
    assert start_error_reports(on) is True
    assert seen["before_send"] is scrub and seen["send_default_pii"] is False
    assert seen["release"] == "abc" and seen["max_request_body_size"] == "never"
