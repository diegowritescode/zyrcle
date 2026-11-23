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
| `api.py` | REST + WebSocket routes for residents and operators |
| `public.py` | Public read-only views: platform totals, a scanned container, host and site dashboards. Aggregates only, no access codes |
| `collection.py`, `collection_routes.py` | Collections ([ADR 0012](../../docs/adr/0012-collection-and-bags.md)): a collector empties a container into bags weighed by its own scale, deposits traced to the collection, mass balances and incidents |
| `sale_routes.py`, `settlement.py`, `domain/settlement.py` | Sales ([ADR 0013](../../docs/adr/0013-sale-and-settlement.md)): the buyer's ticket per bag, the bank match, and the worker that settles each bag on chain (record, residents pro rata minus advance, collector, hosts) |
| `operator_auth.py` | Operator accounts ([ADR 0014](../../docs/adr/0014-operator-accounts.md)): sign-in by email code, operator sessions, admins manage operators; every operator route records who acted |
| `demo.py` | Demo-only routes (mounted when a simulator is configured): containers with their live QR, "drop this item", "take this out", bags standing in for printed labels |
| `models.py`, `migrations/` | Schema; one active session per container enforced by a partial unique index |
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
