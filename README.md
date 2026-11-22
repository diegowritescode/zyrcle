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
| 1 | Deposit session: device simulator over MQTT, state machine, Postgres | planned |
| 2 | ZyrcleChain v2 (own Avalanche L1, native ZYR = 1 COP), Treasury and Settlement contracts | ZyrcleChain v2 live on Fuji; contracts planned |
| 3 | Resident app (Expo) | planned |
| 4 | Collection, sale at the collection center, bank reconciliation, mass balance | planned |
| 5 | Route optimization, deployment, end-to-end demo scenario | planned |

What exists today is still the hackathon product: the deposit and collection flows are simulated
in the API and the frontend talks to contracts on Avalanche Fuji C-Chain. See
[docs/architecture.md](docs/architecture.md) for the target design and [docs/adr](docs/adr) for
the decisions behind it.

## Layout

```
apps/api      FastAPI backend (hackathon API, being replaced in phase 1)
apps/web      Web app (hackathon UI; becomes the operations console)
contracts     Solidity contracts (Hardhat)
infra/l1      ZyrcleChain v2: genesis, validator container, setup scripts
docs          Architecture and decision records
```

## Run locally

API:

```bash
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/uvicorn main:app --reload --port 8000
.venv/bin/pytest
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
