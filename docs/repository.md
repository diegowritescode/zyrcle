# Repository guide

How the monorepo is organised, the conventions every change follows, and how to run it locally.
Design: [architecture.md](architecture.md). Decisions: [adr/](adr/README.md).

## Layout

```
zyrcle/
├── apps/
│   ├── api/            Backend: FastAPI + Postgres + MQTT, workers, CLI (Python 3.13)
│   │   ├── src/zyrcle_api/   application package (one module per area, see its README)
│   │   │   └── domain/       pure logic, no I/O: state machines, verification, slots, settlement split
│   │   ├── migrations/       Alembic revisions 0001..
│   │   ├── tests/            pytest: unit and end-to-end against Postgres, Mosquitto and anvil
│   │   └── dev/              local tooling: dev compose, anvil setup, demo script
│   ├── web/            Web app: landing, dashboards, resident flow, operator console (Vite, React 18)
│   │   └── src/{pages,components,console,wallet,hooks,lib}
│   └── mobile/         Resident and collector app (Expo SDK 58, React Native, Expo Router)
│       └── src/{app,features,account,notifications,wallet,lib,ui,hooks}
├── packages/
│   ├── client/         TypeScript shared by web and mobile: API client, SIWE, QR, labels (ADR 0024)
│   └── protocol/       Python: the signed device protocol, shared by the API and the simulator
├── device/
│   └── simulator/      Simulated container: scale, distance, metal, camera, lock; control panel
├── chain/              Solidity (Foundry): Treasury, AccountFactory, ZyrcleAccount, tests;
│                       lib/safe-smart-account: Safe v1.4.1, vendored (ADR 0040)
├── infra/
│   └── l1/             ZyrcleChain: genesis, validator container, scripts, fuji.env (addresses)
├── deploy/             Production compose stack, deploy script, broker config
├── e2e/                Playwright: every party's journey against the whole system (ADR 0031)
├── docs/               This documentation (map in docs/README.md)
└── .github/workflows/  CI and image release
```

Folders that hold generated or local state are ignored: `node_modules`, `.venv`, `dist`, `out`,
`cache`, `.expo`, `apps/api/dev/.local` (local keys for anvil), `e2e/.stack` (the end-to-end stack's
state and logs), `e2e/test-results` and `e2e/playwright-report`.

## Where a change goes

| You change | Also change |
|---|---|
| A table or column | an Alembic migration (tested up, down and up again on a database with rows), [database.md](database.md) |
| An endpoint | `packages/client` or `apps/web/src/console/api.ts`, a test, [api.md](api.md) |
| A device message | `packages/protocol`, the simulator, [device-protocol.md](device-protocol.md) |
| A contract | `chain/` tests, then `python chain/export-artifacts.py` (CI fails on ABI drift), [infrastructure.md](infrastructure.md) |
| A setting or a service | `config.py`, `deploy/compose.yml`, `deploy/.env.example`, [infrastructure.md](infrastructure.md) |
| A rule, a default, a number that moves money, weight or trust | an ADR or an amendment ([adr/README.md](adr/README.md)) |
| A user-visible flow | [flows.md](flows.md), and its step in `e2e/tests` |

## Conventions

**Languages.** Code, comments, commit messages and repository documents in English. What users see
(apps, emails, push notifications) in Spanish from Colombia, plain and without jargon (ADR 0018).

**Units.** Weights in integer grams, distances in mm, volumes in ml, money in integer pesos off chain
and wei on chain (1e18 wei = 1 COP). Addresses in lowercase `0x`. Time in UTC with time zone; local
days only for aggregates, in `America/Bogota`.

**Python** (`apps/api`, `packages/protocol`, `device/simulator`): Python 3.13, `ruff check` and
`ruff format` (line length 100), type hints, async SQLAlchemy 2. Pure logic goes in `domain/` and
is tested without I/O. Every state change runs in a transaction that locks its row; commands to
devices and live updates are sent only after commit; anything that talks to the outside world
(payouts, push, email, settlement) goes through an outbox table and an idempotent worker.

**TypeScript** (`apps/web`, `apps/mobile`, `packages/client`): strict `tsc`, ESLint (the mobile app
runs the React Compiler rules through `expo lint`). Server data through TanStack Query. No secrets in
`VITE_*` or `EXPO_PUBLIC_*` variables: they end up in the bundle.

**Solidity** (`chain/`): Solidity 0.8.30, Foundry, `forge fmt`, unit, fuzz and invariant tests;
custom errors; roles with OpenZeppelin `AccessControl`.

**Tests.** Every behaviour change comes with a test. The API suite runs end to end against real
Postgres, Mosquitto and anvil, with simulated containers over MQTT. A user-facing change is also
walked through in a real browser before it is called done.

**Commits.** One logical change per commit, subject `area: what changed` (or a milestone title),
body explaining why, and the ADR it implements. Image tags and deploys use the full commit SHA
(ADR 0020).

**Decisions and docs.** ADR 0025: documentation changes in the same commit as the code it describes.

## Run it locally

Prerequisites: Docker, Python 3.13, Node 22 or later (CI uses 22), Foundry (anvil, forge).

```bash
# Backend: Postgres + Mosquitto, migrations, tests
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
dev/mosquitto/make-passwd.sh && docker compose -f dev/compose.yml up -d
.venv/bin/alembic upgrade head && .venv/bin/pytest -q

# Contracts
cd chain && forge soldeer install && forge test

# Shared client, web, mobile
cd packages/client && npm ci && npm test
cd apps/web && npm ci && npm test && npm run dev
cd apps/mobile && npm ci && npm test && npx expo start

# Every party's journey in a browser (e2e/README.md)
e2e/stack/up.sh && e2e/stack/apps.sh && (cd e2e && npm ci && npx playwright test); e2e/stack/down.sh
```

A full local stack (anvil as the chain, the simulator, the API, the web app) is described in
[apps/web/README.md](../apps/web/README.md) and [apps/api/README.md](../apps/api/README.md):
`apps/api/dev/local_chain.py` deploys the Treasury and the account factory on anvil and prints the
variables the API needs.

Do not run the test suite while another local API or simulator uses the same dev broker: they share
device ids and the broker disconnects one of them.
