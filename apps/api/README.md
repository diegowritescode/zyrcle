# Zyrcle API

Backend for deposit sessions: signs residents in with their wallet, talks to containers over MQTT,
runs the session state machine and the material verification, and stores everything in Postgres.
Design: [docs/architecture.md](../../docs/architecture.md), protocol:
[docs/device-protocol.md](../../docs/device-protocol.md).

## Layout

Every file in `src/zyrcle_api/` belongs to one row. Modules were split by responsibility in block 3
([ADR 0036](../../docs/adr/0036-module-boundaries.md)); `sessions.py`, `collection.py` and
`chain.py` each hold one cohesive class and stay whole on purpose.

| Module | What it does |
|---|---|
| `main.py`, `config.py`, `cli.py` | The app factory (routers, workers, rate limits, CORS), the settings read from `ZYRCLE_*` variables, and the `zyrcle-api` command: `serve`, `chain …`, `demo seed`, `keys new`, `safe …` |
| `db.py`, `errors.py`, `live.py` | The async engine and sessions; the errors with a stable `code` that routes turn into HTTP answers; the in-process fan-out of session updates to WebSockets |
| `domain/session_machine.py` | Session states and allowed transitions. Pure, no I/O. |
| `domain/verification.py` | Density, metal and camera checks into one score. Pure. |
| `domain/slots.py` | Hourly turns: opening hours, the 7 bookable days, at most 3 upcoming bookings. Pure. |
| `sessions.py` | Orchestration: row locks, transitions, audit events, commands after commit, timeouts, access-code rotation |
| `mqtt.py` | Broker connection with reconnect and shared subscription |
| `auth.py` | Sign-In with Ethereum (EIP-4361) and JWTs |
| `api.py` | Participant routes: sign-in, sessions and their WebSocket, `/v1/me`, consent, push token |
| `deps.py` | What every route depends on: settings, the session service, the calling resident or operator |
| `setup_routes.py` | Operator routes that set the system up: hosts, sites, schedules, devices, containers, prices, the review queue, health and the Treasury |
| `bookings.py`, `booking_routes.py` | Turns ([ADR 0009](../../docs/adr/0009-time-slots.md)): a container's hours, booking and cancelling, walk-in spots counted under the container lock |
| `email_codes.py`, `recovery.py`, `recovery_worker.py`, `account_routes.py` | Recovery email and lost-phone recovery ([ADR 0010](../../docs/adr/0010-smart-accounts-and-recovery.md)): emailed codes, starting and cancelling a recovery, and the worker that carries it through the chain |
| `mail.py`, `notifications.py` | The email outbox and its worker through Resend; the push outbox and its worker through Expo ([ADR 0008](../../docs/adr/0008-push-notifications.md)) |
| `ipfs.py` | The certificate's public copy pinned on IPFS through Pinata ([ADR 0027](../../docs/adr/0027-impact-certificates.md), amendment) |
| `multisig.py`, `safe_ops.py`, `safe_cli.py` | The Safe that holds the admin powers ([ADR 0040](../../docs/adr/0040-keys-guardian-and-multisig.md)): proposals and their EIP-712 signatures, deploying the Safe, the five-step handover, `zyrcle-api safe …`. Command line only, no API routes |
| `ratelimit.py` | Rate limits per class of route and caller, `429 rate_limited` with `Retry-After` ([ADR 0035](../../docs/adr/0035-rate-limits.md)) |
| `observability.py` | Error reports to Sentry, scrubbed of personal data ([ADR 0033](../../docs/adr/0033-error-reports-and-uptime.md)) |
| `public.py` | Public read-only views: platform totals, a scanned container, host and site dashboards. Aggregates only, no access codes |
| `collection.py`, `collection_routes.py` | Collections ([ADR 0012](../../docs/adr/0012-collection-and-bags.md)): a collector empties a container into bags weighed by its own scale, deposits traced to the collection, mass balances and incidents |
| `sale_routes.py`, `settlement.py`, `domain/settlement.py` | Sales ([ADR 0013](../../docs/adr/0013-sale-and-settlement.md)): the buyer's ticket per bag, the bank match, and the worker that settles each bag on chain (record, residents pro rata minus advance, collector, hosts) |
| `centers.py`, `center_routes.py` | Collection centers ([ADR 0037](../../docs/adr/0037-prices-per-collection-center.md)): the centers, their price per material, the price an advance uses (the site's center, else the general table), and the median of the last 90 days of confirmed sales as a suggestion |
| `tickets.py`, `ticket_routes.py` | The scale ticket read from a photo with Claude ([ADR 0038](../../docs/adr/0038-reading-scale-tickets-with-ai.md)): structured output, arithmetic checks, proposed bags; a person confirms. Off without an Anthropic key |
| `bank.py`, `bank_routes.py` | The bank statement ([ADR 0039](../../docs/adr/0039-bank-statement-matching.md)): CSV or Excel parsed (pure), each movement proposed for a sale or a redemption with a score, matched with one click |
| `impact.py`, `impact_routes.py`, `domain/impact.py` | Impact certificates ([ADR 0027](../../docs/adr/0027-impact-certificates.md)): monthly per host or site, sold material only, EPA WARM v16 factors, the claim ledger, the Merkle root and the worker that anchors it on chain |
| `payments.py`, `payment_routes.py` | Campus merchants ([ADR 0029](../../docs/adr/0029-closed-loop-payments.md)): charges with a QR, the payer's signed `Execute` checked and relayed with the guardian key (deploying the account if needed), redemptions of ZYR for pesos settled or refunded by the operator |
| `health.py` | Health report for the console and admin email alerts ([ADR 0028](../../docs/adr/0028-pilot-readiness.md)): outboxes, devices, broker, chain head, Treasury, gas of the hot keys. A quiet chain is not a stalled one: it warns only when work has waited as long as the last block is old, and asks the node's `/ext/health` (amendment) |
| `operator_auth.py` | Operator accounts ([ADR 0014](../../docs/adr/0014-operator-accounts.md)): sign-in by email code, operator sessions, admins manage operators; every operator route records who acted |
| `demo.py`, `demo_seed.py` | Demo-only routes (mounted when a simulator is configured): containers with their live QR, "drop this item", "take this out", bags standing in for printed labels; and the idempotent seed of the demo host, sites and simulated containers |
| `models/`, `migrations/` | Schema: a package with one module per area on a shared `base.py` (places, participants, deposits, money, messaging, collection, sales, operators, impact, payments, centers, bank), and migrations `0001` to `0016` ([docs/database.md](../../docs/database.md)) |
| `pricing.py`, `payouts.py`, `chain.py` | Advance sizing, the payout outbox worker, and the client of the contracts (web3.py) |
| `contracts/` | The compiled contracts the backend uses (ABI and bytecode): Treasury, AccountFactory, ZyrcleAccount, and Safe v1.4.1 (SafeL2, SafeProxyFactory, CompatibilityFallbackHandler, MultiSendCallOnly). CI fails if they drift from `chain/` |

## Guarantees and how they are enforced

| Guarantee | Mechanism |
|---|---|
| One resident at a time per container | Partial unique index on active sessions; concurrent requests get 409 |
| Nobody deposits while a container is emptied, and the reverse | Both lock the container row before checking for the other; one active collection per container (partial unique index) |
| Collectors never declare a weight | A bag's grams are two signed scale readings apart; mass balances open incidents |
| A container cannot act on a session the DB has not stored | Commands are sent only after commit |
| Forged, replayed or duplicated device messages change nothing | ECDSA signature per device, strictly increasing `seq`, `(device_id, seq)` primary key |
| A device cannot speak for another | Broker ACL plus device id check on every envelope |
| Old QR photos are useless | Access codes rotate every 30 s; the previous one stays valid until it expires |
| Every change is auditable | Append-only `session_event`, raw signed messages in `device_message` |
| Live clients never see an uncommitted state | WebSocket updates are published after commit |
| Timeouts work with several replicas | Sweeper uses `SELECT … FOR UPDATE SKIP LOCKED` |
| A sale settles once, and only after the money reached the bank | Nothing goes on chain before the operator confirms the bank match; each step checks the chain first (`sales`, `depositSettled`, parts already paid) and the contract refuses double payments |
| A credited deposit is always paid, exactly once | Payout written in the crediting transaction (outbox); worker checks `advanceOf` before resending; the contract refuses a second advance |
| One gram, one claim | Unique `(session_id, attribute)` in the claim ledger; a second certificate over the same deposit fails |
| A bank movement pays one sale or redemption, once | Unique fingerprint per movement (a re-uploaded statement adds nothing) and unique `matched_id`; the operator confirms every match |
| Nothing a model read is saved without a person | A ticket scan only fills the form; the operator records the sale |
| A burst from one caller does not slow the others | Token buckets per account, or per IP address without one |

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
dev/mosquitto/make-passwd.sh                     # dev broker users, password "dev-password"
docker compose -f dev/compose.yml up -d          # Postgres + Mosquitto with the ACL
.venv/bin/alembic upgrade head
cp .env.example .env                             # fill in the two secrets
.venv/bin/zyrcle-api serve                       # http://127.0.0.1:8000/docs
.venv/bin/python dev/demo.py                     # PET, stone and walk-away scenarios
```

Optional services stay off until their key is set: `ZYRCLE_RESEND_API_KEY` (or
`ZYRCLE_EMAIL_LOG_ONLY=true`) for email, `ZYRCLE_PINATA_JWT` for the certificates' IPFS copy,
`ZYRCLE_ANTHROPIC_API_KEY` for reading tickets, `ZYRCLE_SENTRY_DSN` for error reports. Every
setting is in [`config.py`](src/zyrcle_api/config.py).

## Tests

```bash
.venv/bin/pytest -q
.venv/bin/pytest -q --cov --cov-report=term      # coverage; CI fails under 75 % (ADR 0031)
```

Unit tests cover the state machine (including random event sequences with Hypothesis) and the
verification rules. End-to-end tests run the real app against Postgres and Mosquitto with simulated
containers: PET verified, stone to review, walk-away credited, empty deposit, busy container, bad
codes, replayed and forged messages, broker ACL, SIWE nonce reuse, the live WebSocket, and the
public views (a paid deposit shows up in the totals, the site dashboard and the resident's
history). `test_auth.py` parses the exact SIWE message the web app signs. Chain
end-to-end tests deploy the Treasury on anvil with the backend's own code and check that verified
or approved deposits land as ZYR in the resident's wallet, capped, and never twice (needs Foundry's
`anvil` on the PATH; skipped otherwise); the Safe tests check that a proposal needs two owners'
signatures and that the five-step handover leaves the admin key with no power, on anvil. Block 3
added tests for rate limits, scrubbed error reports, center prices, ticket reading against a
stand-in for Claude, and statement parsing and matching. Every party's journey in a browser lives
in [`e2e/`](../../e2e/README.md).
