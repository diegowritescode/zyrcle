# Zyrcle API

Backend for deposit sessions: signs residents in with their wallet, talks to containers over MQTT,
runs the session state machine and the material verification, and stores everything in Postgres.
Design: [docs/architecture.md](../../docs/architecture.md), protocol:
[docs/device-protocol.md](../../docs/device-protocol.md).

## Layout

| Module | What it does |
|---|---|
| `domain/session_machine.py` | Session states and allowed transitions. Pure, no I/O. |
| `domain/verification.py` | Density, metal and camera checks into one score. Pure. |
| `sessions.py` | Orchestration: row locks, transitions, audit events, commands after commit, timeouts, access-code rotation |
| `mqtt.py` | Broker connection with reconnect and shared subscription |
| `auth.py` | Sign-In with Ethereum (EIP-4361) and JWTs |
| `api.py` | Participant routes: sign-in, sessions and their WebSocket, `/v1/me` |
| `deps.py` | What every route depends on: settings, the session service, the calling resident or operator |
| `setup_routes.py` | Operator routes that set the system up: hosts, sites, schedules, devices, containers, prices, the review queue |
| `email_codes.py`, `recovery.py`, `recovery_worker.py`, `account_routes.py` | Recovery email and lost-phone recovery ([ADR 0010](../../docs/adr/0010-smart-accounts-and-recovery.md)): emailed codes, starting and cancelling a recovery, and the worker that carries it through the chain |
| `ipfs.py` | The certificate's public copy pinned on IPFS through Pinata ([ADR 0027](../../docs/adr/0027-impact-certificates.md), amendment) |
| `multisig.py`, `safe_ops.py`, `safe_cli.py` | The Safe that takes the admin powers ([ADR 0040](../../docs/adr/0040-keys-guardian-and-multisig.md)): proposals and their EIP-712 signatures, deploying the Safe, the five-step handover, `zyrcle-api safe …` |
| `ratelimit.py` | Rate limits per class of route and caller ([ADR 0035](../../docs/adr/0035-rate-limits.md)) |
| `observability.py` | Error reports to Sentry, scrubbed of personal data ([ADR 0033](../../docs/adr/0033-error-reports-and-uptime.md)) |
| `public.py` | Public read-only views: platform totals, a scanned container, host and site dashboards. Aggregates only, no access codes |
| `collection.py`, `collection_routes.py` | Collections ([ADR 0012](../../docs/adr/0012-collection-and-bags.md)): a collector empties a container into bags weighed by its own scale, deposits traced to the collection, mass balances and incidents |
| `sale_routes.py`, `settlement.py`, `domain/settlement.py` | Sales ([ADR 0013](../../docs/adr/0013-sale-and-settlement.md)): the buyer's ticket per bag, the bank match, and the worker that settles each bag on chain (record, residents pro rata minus advance, collector, hosts) |
| `impact.py`, `impact_routes.py`, `domain/impact.py` | Impact certificates ([ADR 0027](../../docs/adr/0027-impact-certificates.md)): monthly per host or site, sold material only, EPA WARM v16 factors, the claim ledger, the Merkle root and the worker that anchors it on chain |
| `payments.py`, `payment_routes.py` | Campus merchants ([ADR 0029](../../docs/adr/0029-closed-loop-payments.md)): charges with a QR, the payer's signed `Execute` checked and relayed with the guardian key (deploying the account if needed), redemptions of ZYR for pesos settled or refunded by the operator |
| `health.py` | Health report for the console and admin email alerts ([ADR 0028](../../docs/adr/0028-pilot-readiness.md)): outboxes, devices, broker, chain head, Treasury, gas of the hot keys |
| `operator_auth.py` | Operator accounts ([ADR 0014](../../docs/adr/0014-operator-accounts.md)): sign-in by email code, operator sessions, admins manage operators; every operator route records who acted |
| `demo.py` | Demo-only routes (mounted when a simulator is configured): containers with their live QR, "drop this item", "take this out", bags standing in for printed labels |
| `models/`, `migrations/` | Schema, one module per area (places, participants, deposits, money, messaging, collection, sales, operators, impact, payments); one active session per container enforced by a partial unique index |
| `pricing.py`, `payouts.py`, `chain.py` | Advance sizing, the payout outbox worker, and the Treasury client (web3.py) |

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

## Tests

```bash
.venv/bin/pytest -q
```

Unit tests cover the state machine (including random event sequences with Hypothesis) and the
verification rules. End-to-end tests run the real app against Postgres and Mosquitto with simulated
containers: PET verified, stone to review, walk-away credited, empty deposit, busy container, bad
codes, replayed and forged messages, broker ACL, SIWE nonce reuse, the live WebSocket, and the
public views (a paid deposit shows up in the totals, the site dashboard and the resident's
history). `test_auth.py` parses the exact SIWE message the web app signs. Chain
end-to-end tests deploy the Treasury on anvil with the backend's own code and check that verified
or approved deposits land as ZYR in the resident's wallet, capped, and never twice (needs Foundry's
`anvil` on the PATH; skipped otherwise).
