# Zyrcle

Verifiable recycling traceability: material is weighed at the container where a household drops it,
followed to the collection center that buys it, and the household is paid out of what the buyer
actually paid.

**Live demo: https://zyrcle.deviego.xyz** (simulated containers, real backend, real L1 on Avalanche
Fuji; ZYR has no real value on testnet). Scan a container, drop items, tap "Terminé" and the advance
lands in your wallet in a few seconds. Open a container's screen (`/container/ctr-0001`) on one
device and scan it with the phone from another to see the real flow.

Zyrcle started as a one-day hackathon project (May 2025, first place). It is now being rebuilt
properly ([history](docs/history.md)). The hackathon state is preserved at tag
[`v0-hackathon`](../../tree/v0-hackathon).

**Documentation:** [docs/README.md](docs/README.md) is the map: architecture, step-by-step flows with
diagrams, the API, the database, infrastructure and operation, the repository guide, and every
decision with who made it ([docs/adr](docs/adr/README.md)).

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Monorepo, cleanup of the hackathon code, CI | done |
| 1 | Deposit session: device simulator over MQTT, state machine, Postgres | done |
| 2 | ZyrcleChain v2 (own Avalanche L1, native ZYR = 1 COP), Treasury contract, payouts | done: live on Fuji, advances paid on chain |
| 3 | Resident app (Expo) | in progress: deposit flow, wallet, history, hourly turns, push notifications, and lost-phone recovery (smart accounts, recovery email) working |
| 4 | Collection, sale at the collection center, bank reconciliation, mass balance | built in the v1 block ([roadmap](docs/roadmap-v1.md)): bags weighed by the container, sales confirmed against the bank, settlement to residents, collector and host on chain |
| 5 | Deployment and live demo | done: the hackathon web app, wired to the new backend |

The deposit cycle works end to end: a signed device protocol, a container simulator with all its
sensors, a backend that runs the session state machine and the anti-cheating checks, and a Treasury
on the project's own L1 that pays the advance in ZYR. The web app keeps the hackathon design and
now runs on real data: live platform totals, the resident flow (QR scan, live weight, verdict,
payment) with an embedded wallet or MetaMask/Core, and the dashboard of each host (a university, a residential complex) and its sites. Collectors and
sales (phase 4) are marked as coming next. Route optimization comes after phase 4. See
[docs/architecture.md](docs/architecture.md) for the design and [docs/adr](docs/adr/README.md)
for every decision behind it, with who made it and when.

## Layout

```
apps/api          Backend: deposit sessions, device link, verification, payouts, public views
apps/web          Web app: the hackathon design on the new API (React, viem, Tailwind, shadcn/ui)
apps/mobile       Resident app (Expo, React Native): scan, deposit, get paid
packages/client   API client, SIWE message, QR codes and labels shared by web and mobile
packages/protocol Device protocol shared by the API and the simulator
device/simulator  Simulated container: scale, distance, metal, camera, lock
chain             Treasury contract (Foundry)
infra/l1          ZyrcleChain v2: genesis, validator container, setup scripts
deploy            Production compose stack and deploy script
docs              Architecture and decision records
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

Web, against a full local stack (anvil as the chain, the simulator, the API): see
[apps/web/README.md](apps/web/README.md).

Treasury contract:

```bash
cd chain
forge soldeer install && forge test
```

## License

Proprietary, all rights reserved. The code is public to be read and evaluated, not reused: see
[LICENSE](LICENSE). Third-party libraries keep their own licenses.
