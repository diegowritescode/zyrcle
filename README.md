# Zyrcle

Verifiable recycling traceability: material is weighed at the container where a household drops it,
followed to the collection center that buys it, and the household is paid out of what the buyer
actually paid.

Zyrcle started as a one-day hackathon project (May 2025, first place). It is now being rebuilt
properly. The hackathon state is preserved at tag [`v0-hackathon`](../../tree/v0-hackathon).

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Monorepo, cleanup of the hackathon code, CI | done |
| 1 | Deposit session: device simulator over MQTT, state machine, Postgres | done |
| 2 | ZyrcleChain v2 (own Avalanche L1, native ZYR = 1 COP), Treasury and Settlement contracts | ZyrcleChain v2 live on Fuji; Treasury built and tested |
| 3 | Resident app (Expo) | planned |
| 4 | Collection, sale at the collection center, bank reconciliation, mass balance | planned |
| 5 | Route optimization, deployment, end-to-end demo scenario | planned |

The deposit flow is rebuilt (phase 1): a signed device protocol, a container simulator with all
its sensors, and a backend that runs the session state machine and the anti-cheating checks. The
web app is still the hackathon UI and talks to the old API in `apps/api-legacy`. See
[docs/architecture.md](docs/architecture.md) for the target design and [docs/adr](docs/adr) for
the decisions behind it.

## Layout

```
apps/api          Backend: deposit sessions, device link, verification (phase 1)
apps/api-legacy   Hackathon API, kept until the web app is rewritten
apps/web          Web app (hackathon UI; becomes the operations console)
packages/protocol Device protocol shared by the API and the simulator
device/simulator  Simulated container: scale, distance, metal, camera, lock
contracts     Solidity contracts (Hardhat)
infra/l1      ZyrcleChain v2: genesis, validator container, setup scripts
chain         Treasury contract (Foundry)
docs          Architecture and decision records
```

## Run locally

Backend, broker, database and simulated containers: see [apps/api/README.md](apps/api/README.md).
The short version:

```bash
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
dev/mosquitto/make-passwd.sh && docker compose -f dev/compose.yml up -d
.venv/bin/alembic upgrade head && .venv/bin/pytest -q
```

Web:

```bash
cd apps/web
npm ci
cp .env.example .env
npm run dev   # http://localhost:8080
```

Contracts:

```bash
cd contracts
npm ci
npx hardhat test
```
