"""SIWE parsing against the exact message the web app builds."""

from datetime import UTC, datetime

from zyrcle_api.auth import parse_siwe

# Built by apps/web/src/lib/siwe.ts; the same literal is asserted in apps/web/src/lib/siwe.test.ts.
# Browsers write the timestamp with a trailing "Z" (Date.toISOString), Python with "+00:00".
WEB_MESSAGE = "\n".join(
    [
        "zyrcle.test wants you to sign in with your Ethereum account:",
        "0x52908400098527886E0F7030069857D2E4169EE7",
        "",
        "Sign in to Zyrcle.",
        "",
        "URI: https://zyrcle.test",
        "Version: 1",
        "Chain ID: 20261121",
        "Nonce: abc123XYZ",
        "Issued At: 2026-11-22T15:30:00.123Z",
    ]
)


def test_parses_the_message_the_web_app_signs():
    m = parse_siwe(WEB_MESSAGE)
    assert m.domain == "zyrcle.test"
    assert m.address.lower() == "0x52908400098527886e0f7030069857d2e4169ee7"
    assert m.chain_id == 20261121
    assert m.nonce == "abc123XYZ"
    assert m.issued_at == datetime(2026, 11, 22, 15, 30, 0, 123000, tzinfo=UTC)
