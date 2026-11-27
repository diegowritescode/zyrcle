# Zyrcle

Verifiable recycling traceability: material is weighed at the container where a household drops it,
followed to the collection center that buys it, and the household is paid out of what the buyer
actually paid.

**Live demo: https://zyrcle.deviego.xyz** (simulated containers, real backend at
`https://zyrcle-backend.deviego.xyz`, real L1 on Avalanche Fuji; ZYR has no real value on
testnet). Scan a container, drop items, tap "Terminé" and the advance lands in your wallet in a few
seconds. Open a container's screen (`/container/ctr-0001`) on one device and scan it with the phone
from another to see the real flow.

Zyrcle started as a one-day hackathon project (May 2025, first place) and has been rebuilt since
November 2026 ([history](docs/history.md)). The hackathon state is preserved at tag
[`v0-hackathon`](https://github.com/diegowritescode/zyrcle/tree/v0-hackathon).

**Documentation:** [docs/README.md](docs/README.md) is the map: architecture, step-by-step flows
with diagrams, the API, the database, infrastructure and operation, the repository guide, the
roadmap, and every decision with who made it ([docs/adr](docs/adr/README.md)).

## Status

| Stage | Scope | State |
|---|---|---|
| Rebuild, phases 0 to 2 | Monorepo and CI; the deposit session over MQTT with a container simulator; ZyrcleChain v2 (own Avalanche L1, native ZYR = 1 COP), the Treasury and advances paid on chain | done, live on Fuji |
| Rebuild, phase 3 | Resident app (Expo): deposit, wallet, history, hourly turns, push notifications, lost-phone recovery with smart accounts | done; Android builds through EAS, on Diego's Mac since 2026-11-25 ([ADR 0015](docs/adr/0015-android-builds.md), [ADR 0043](docs/adr/0043-android-builds-on-the-mac.md)) |
| v1 block 1 (M1 to M4) | Hosts and sites, collection into bags weighed by the container, sale and settlement, operator console | deployed ([roadmap](docs/roadmap-v1.md)) |
| v1 block 2 (M5 to M7) | Impact certificates with a permanent copy on IPFS, campus merchants with QR payments and redemptions (Treasury v3), pilot readiness | deployed |
| Block 3 (M8 to M17) | Every party's journey tested in CI, deploys pinned by digest, error reports and an uptime check, encrypted off-site backups, rate limits, modules split, collection centers with their prices, scale tickets read from a photo, bank statement matching, a key of its own for the guardian, and a 2-of-3 Safe holding every admin power | deployed on 2026-11-23 ([roadmap](docs/roadmap-blocks-3-4.md)); the Safe holds the admin powers since that day. Error reports, off-site copies and ticket reading stay off until their accounts exist; the guardian keeps the oracle key until [runbook 9.13](docs/infrastructure.md#913-give-the-guardian-its-own-key) runs |
| Block 4 (M18 to M23) | What each party sees: participant, collector, host, merchant, a collection center portal, a new Android build | M18 and M19 built (each deposit's steps, personal impact, where to spend, fill alerts, collector earnings; [ADR 0041](docs/adr/0041-participant-timeline-impact-and-where-to-spend.md), [ADR 0042](docs/adr/0042-collector-fill-alerts-and-earnings.md)), deployed 2026-11-26; M20 to M23 planned |

The loop closes end to end, on simulated containers: a signed device protocol, a container
simulator with all its sensors, a backend that runs the session state machine and the anti-cheating
checks, and a Treasury on the project's own L1 that pays an advance in ZYR at the deposit and the
rest when the material is sold and the pesos reach the bank. The web app keeps the hackathon design
and runs on real data: live platform totals, the resident flow (QR scan, live weight, verdict,
payment) with an embedded wallet or MetaMask/Core, the dashboard of each host (a university, a
residential complex) and its sites, impact certificates checked in the browser against the chain,
the operator console at `/console`, and the page where the Safe's owners sign at `/multisig`. The
mobile app is where participants deposit and pay, collectors empty containers, and merchants charge.
See [docs/architecture.md](docs/architecture.md) for the design and [docs/adr](docs/adr/README.md)
for every decision behind it, with who made it and when.

## Layout

```
apps/api          Backend: deposits, device link, collection, sales and settlement, payments,
                  certificates, the operator's routes, workers, CLI (FastAPI, Postgres)
apps/web          Web app: the hackathon design on the new API, the console, the multisig page
apps/mobile       Resident, collector and merchant app (Expo, React Native)
packages/client   API client, SIWE message, QR codes, labels and error scrubbing for web and mobile
packages/protocol Device protocol shared by the API and the simulator
device/simulator  Simulated container: scale, distance, metal, camera, lock
chain             Treasury, AccountFactory and smart accounts (Foundry); Safe v1.4.1 vendored
infra/l1          ZyrcleChain v2: genesis, validator container, scripts, addresses, Safe proposals
deploy            Production compose stack, deploy script, backups on the VPS and off it
e2e               Every party's journey in a real browser against the whole system (Playwright)
docs              Architecture, flows, API, database, operation and decision records
.github/workflows CI, image release, uptime check
```

## Run locally

Backend, broker, database and simulated containers: see [apps/api/README.md](apps/api/README.md).
The short version:

```bash
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -r requirements-dev.txt
dev/mosquitto/make-passwd.sh && docker compose -f dev/compose.yml up -d
.venv/bin/alembic upgrade head && .venv/bin/pytest -q
```

Web, against a full local stack (anvil as the chain, the simulator, the API): see
[apps/web/README.md](apps/web/README.md).

Contracts:

```bash
cd chain
forge soldeer install && forge test
```

Every party's journey in a browser, against the whole system started from the checkout (needs the
broker and Postgres above, Foundry, Node 22 and Google Chrome): see [e2e/README.md](e2e/README.md).

```bash
(cd apps/web && npm ci) && (cd apps/mobile && npm ci) && (cd e2e && npm ci)
e2e/stack/up.sh && e2e/stack/apps.sh && (cd e2e && npx playwright test)
e2e/stack/down.sh   # before the backend tests: both use the same device ids
```

More, for every part of the repository: [docs/repository.md](docs/repository.md).

## License

Proprietary, all rights reserved. The code is public to be read and evaluated, not reused: see
[LICENSE](LICENSE). Third-party libraries keep their own licenses.
