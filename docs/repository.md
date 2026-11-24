# Repository guide

How the monorepo is organised, the conventions every change follows, and how to run it locally.
Design: [architecture.md](architecture.md). Decisions: [adr/](adr/README.md).

## Layout

```
zyrcle/
├── apps/
│   ├── api/            Backend: FastAPI + Postgres + MQTT, workers, CLI (Python 3.13)
│   │   ├── src/zyrcle_api/   application package, one module per responsibility (ADR 0036)
│   │   │   ├── models/       the tables, one module per area, all re-exported by the package
│   │   │   ├── domain/       pure logic, no I/O: state machines, verification, slots, settlement
│   │   │   └── contracts/    compiled ABIs and bytecode, exported from chain/
│   │   ├── migrations/       Alembic revisions 0001..
│   │   ├── tests/            pytest: unit and end-to-end against Postgres, Mosquitto and anvil
│   │   └── dev/              local tooling: dev compose, anvil setup, demo script
│   ├── web/            Web app: landing, dashboards, resident flow, console, /multisig (React 18)
│   │   └── src/{pages,components,console,wallet,hooks,lib,content}
│   └── mobile/         Resident, collector and merchant app (Expo SDK 58, Expo Router)
│       └── src/{app,features,account,notifications,wallet,lib,ui,hooks}
├── packages/
│   ├── client/         TypeScript shared by web and mobile: API client, SIWE, QR, certificate
│   │                   check, error scrubbing, labels (ADR 0024)
│   └── protocol/       Python: the signed device protocol, shared by the API and the simulator
├── device/
│   └── simulator/      Simulated container: scale, distance, metal, camera, lock; control panel
├── chain/              Solidity (Foundry): Treasury, AccountFactory, ZyrcleAccount, the Safe's
│                       imports, tests
│   └── lib/safe-smart-account/   Safe v1.4.1, vendored unchanged (ADR 0040)
├── infra/
│   └── l1/             ZyrcleChain: genesis, validator container, scripts, fuji.env (addresses)
│       └── safe/       every executed Safe proposal, signed: the record of admin changes
├── deploy/             Production compose stack, deploy script, backups on the VPS and off it
│                       (backup.sh, offsite.sh), broker config
├── e2e/                Playwright: every party's journey against the whole system (ADR 0031)
│   ├── stack/          start and stop the system from the checkout, with Pinata, IPFS and
│   │                   Anthropic stand-ins
│   └── tests/          the journeys: a day on campus, a lost phone, the Safe
├── docs/               This documentation (map in docs/README.md)
└── .github/            workflows: CI, image release, uptime check; Dependabot for base images
```

Folders that hold generated or local state are ignored: `node_modules`, `.venv`, `dist`, `out`,
`cache`, `chain/dependencies` (Soldeer's packages), `.expo`, `apps/api/dev/.local` (local keys for
anvil), `e2e/.stack` (the end-to-end stack's state and logs), `e2e/test-results`,
`e2e/playwright-report` and coverage reports. `deploy/.env` and `deploy/history.log` exist only on
the VPS.

## Where a change goes

| You change | Also change |
|---|---|
| A table or column | its model in `apps/api/src/zyrcle_api/models/` (the module of its area, exported from `models/__init__.py`), an Alembic migration (tested up, down and up again on a database with rows; CI checks the models match with `alembic check`), [database.md](database.md) |
| An endpoint | the routes module of its area, `packages/client` or `apps/web/src/console/api.ts`, a test, [api.md](api.md); a route that sends or checks emailed codes, or signs in, also goes in `CODE_ROUTES` or `SIGNIN_ROUTES` of `ratelimit.py` (ADR 0035) |
| A device message | `packages/protocol`, the simulator, [device-protocol.md](device-protocol.md) |
| A contract | `chain/` tests, then `python chain/export-artifacts.py` into `apps/api/src/zyrcle_api/contracts/` (CI fails on ABI drift), [infrastructure.md](infrastructure.md) |
| A setting or a service | `config.py`, `deploy/compose.yml`, `deploy/.env.example`, [infrastructure.md](infrastructure.md) |
| An external service | off without its key in `config.py`, a stand-in in `e2e/stack/fake-services.mjs` and in the backend tests, `apps/web/security-headers.conf` if the browser reaches it, [architecture.md](architecture.md) section 12 |
| What an error report may carry | the scrubbing rules in both `observability.py` and `packages/client/src/scrub.ts`, with their tests (ADR 0033) |
| A base image or a service image | its pinned digest; Dependabot proposes the updates as pull requests (ADR 0032) |
| An admin power on ZyrcleChain: roles, precompiles, validators, the guardian | a Safe proposal (`zyrcle-api safe propose`) signed by two owners, then the executed file in `infra/l1/safe/` ([flows.md](flows.md#signing-a-safe-proposal), runbook 9.14 in [infrastructure.md](infrastructure.md)) |
| An address on ZyrcleChain | `infra/l1/fuji.env` |
| A rule, a default, a number that moves money, weight or trust | an ADR or an amendment ([adr/README.md](adr/README.md)) |
| A user-visible flow | [flows.md](flows.md), and its step in `e2e/tests` |

## Conventions

**Languages.** Code, comments, commit messages and repository documents in English. What users see
(apps, emails, push notifications) in Spanish from Colombia, plain and without jargon (ADR 0018).

**Units.** Weights in integer grams, distances in mm, volumes in ml, money in integer pesos off
chain and wei on chain (1e18 wei = 1 COP). Addresses in lowercase `0x`. Time in UTC with time zone;
local days only for aggregates, in `America/Bogota`.

**Python** (`apps/api`, `packages/protocol`, `device/simulator`): Python 3.13, `ruff check` and
`ruff format` (line length 100), type hints, async SQLAlchemy 2. Pure logic goes in `domain/` and
is tested without I/O. Every state change runs in a transaction that locks its row; commands to
devices and live updates are sent only after commit; anything that pays, notifies or settles
(payouts, push, email, settlement, certificate anchors, relayed payments, recoveries) goes through
an outbox table and an idempotent worker. Two steps a person waits on in the console call out
inside the request instead: reading a ticket photo, and settling or refunding a redemption.

**TypeScript** (`apps/web`, `apps/mobile`, `packages/client`): strict `tsc`, ESLint (the mobile
app runs the React Compiler rules through `expo lint`). Server data through TanStack Query. No
secrets in `VITE_*` or `EXPO_PUBLIC_*` variables: they end up in the bundle. The journeys in `e2e/`
are type-checked with `tsc` too.

**Solidity** (`chain/`): Solidity 0.8.30, Foundry, `forge fmt`, unit, fuzz and invariant tests;
custom errors; roles with OpenZeppelin `AccessControl`.

**Tests.** Every behaviour change comes with a test. The API suite runs end to end against real
Postgres, Mosquitto and anvil, with simulated containers over MQTT. A user-facing change also gets
its step in the Playwright journeys in `e2e/`, which CI runs on every push and pull request against
the whole system (ADR 0031). Coverage has floors that only go up: 75 % of lines for the API and 50 %
for the shared client; the web app's is shown without a floor.

**Commits.** One logical change per commit, subject `area: what changed` (or a milestone title),
body explaining why, and the ADR it implements. Images are tagged with the full commit SHA
(ADR 0020), published only when CI passed, and deployed by digest (ADR 0032).

**Decisions and docs.** ADR 0025: documentation changes in the same commit as the code it describes.

## Run it locally

Prerequisites: Docker, Python 3.13, Node 22 or later (CI uses 22), Foundry (anvil, forge), and
Google Chrome for the end-to-end journeys.

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

# Every party's journey in a browser (e2e/README.md), after the web and mobile npm ci above
(cd e2e && npm ci) && e2e/stack/up.sh && e2e/stack/apps.sh && (cd e2e && npx playwright test)
e2e/stack/down.sh   # before the backend tests again: both use the same device ids
```

A full local stack (anvil as the chain, the simulator, the API, the web app) is described in
[apps/web/README.md](../apps/web/README.md) and [apps/api/README.md](../apps/api/README.md):
`apps/api/dev/local_chain.py` deploys the Treasury and the account factory on anvil and prints the
variables the API needs.

Do not run the test suite while another local API or simulator uses the same dev broker: they share
device ids and the broker disconnects one of them.
