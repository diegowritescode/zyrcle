# Zyrcle infrastructure

This document describes how Zyrcle runs in production, how it is built and released, and how to
operate or rebuild it. It is written for the engineer who keeps it running.

> Checked against commit `fd05fa7` (2026-11-23) and the decision records up to ADR 0040.
> Production runs the images of commit `0d41852d7d836cd2a797b5673b8c1adc0e73ef8b` (blocks 1 to 3, block 4's M18 and M19
> and the Sentry fix, [ADR 0030](adr/0030-blocks-3-and-4.md), deployed 2026-11-26 at 05:36 UTC,
> migration 0017).
> Every statement comes from a file in this repository. When something is not in the repository,
> this document says so.

Shorter, component-level guides: [deploy/README.md](../deploy/README.md),
[infra/l1/README.md](../infra/l1/README.md), [chain/README.md](../chain/README.md),
[apps/mobile/README.md](../apps/mobile/README.md), [e2e/README.md](../e2e/README.md). Running the
code on a laptop: [repository.md](repository.md). Threats and defences:
[security.md](security.md). The decisions behind this setup:
[ADR 0020](adr/0020-single-vps-docker-compose.md) (one VPS),
[ADR 0021](adr/0021-l1-operations.md) (L1 operations),
[ADR 0022](adr/0022-keys-secrets-and-production-changes.md) (keys and who may change production),
[ADR 0032](adr/0032-deploys-pinned-recorded-and-backed-up.md) (deploys pinned and recorded),
[ADR 0033](adr/0033-error-reports-and-uptime.md) (error reports and uptime),
[ADR 0034](adr/0034-encrypted-off-site-backups.md) (off-site backups) and
[ADR 0040](adr/0040-keys-guardian-and-multisig.md) (the guardian's key and the admin Safe).

## Contents

1. [Terms](#1-terms)
2. [Deployment diagram](#2-deployment-diagram)
3. [Environments](#3-environments)
4. [Production services](#4-production-services)
5. [Configuration](#5-configuration)
6. [Secrets and keys](#6-secrets-and-keys)
7. [ZyrcleChain](#7-zyrclechain)
8. [CI/CD](#8-cicd)
9. [Runbooks](#9-runbooks)
10. [Known gaps and risks](#10-known-gaps-and-risks)

## 1. Terms

| Term | Meaning in this document |
|---|---|
| VPS | Virtual private server. The one rented Linux machine (`aitera-vps`) that runs everything. It also runs Diego's other projects behind the same Traefik ([ADR 0020](adr/0020-single-vps-docker-compose.md)). |
| Docker Compose | A tool that starts a set of containers from a YAML file. A *compose project* is one such set, with its own name, networks and volumes. |
| Traefik | The reverse proxy already running on the VPS. It accepts HTTPS, terminates TLS (the encryption layer) and forwards each request to a container by host name. Its configuration is not in this repository. |
| GHCR | GitHub Container Registry. The release workflow pushes images there. |
| Full commit SHA | The 40-character hexadecimal ID of a git commit. Every image tag is one. |
| Digest | The `sha256:…` hash of an image's content. `repository@sha256:…` names one exact image, which a tag cannot guarantee. Production runs images by digest ([ADR 0032](adr/0032-deploys-pinned-recorded-and-backed-up.md)). |
| Dependabot | GitHub's service that opens pull requests to update pinned images and actions ([.github/dependabot.yml](../.github/dependabot.yml)). |
| GitHub Actions | GitHub's automation service. It runs the files in `.github/workflows/`. |
| CI | Continuous integration: the checks that run on every push and pull request. |
| EAS | Expo Application Services. Expo's cloud service that builds the mobile app. |
| Expo push service | Expo's HTTPS service that forwards push notifications to Google and Apple. |
| FCM, APNs | Firebase Cloud Messaging (Google's push service for Android) and Apple Push Notification service. |
| Resend | An email delivery service with an HTTP API. The API sends codes and alerts through it. |
| MQTT, broker | MQTT is a light publish/subscribe protocol for devices. The broker is the server that relays the messages; here it is Mosquitto. |
| ACL | Access control list: which broker user may publish or read which topic. |
| Alembic, migration | Alembic is the database migration tool. A migration moves the schema from one revision to the next. |
| Avalanche L1 | A blockchain with its own validators, registered on Avalanche's P-Chain. ZyrcleChain is one. |
| Fuji | Avalanche's public test network. Its coins have no value. |
| P-Chain, C-Chain | Avalanche's platform chain (records L1s and validators, charges validator fees) and its main EVM chain. |
| Subnet-EVM | Avalanche's Ethereum-compatible virtual machine for L1s. |
| Precompile | A built-in contract at a fixed address that the chain implements natively, for example the NativeMinter. |
| Validator | A node that produces and confirms blocks. ZyrcleChain has one. |
| Continuous validator fee | Since ACP-77, an L1 validator keeps an AVAX balance on the P-Chain, and the P-Chain deducts a fee from it continuously. At zero the validator stops ([ADR 0021](adr/0021-l1-operations.md)). |
| anvil | Foundry's local Ethereum node. Development and tests use it in place of ZyrcleChain. |
| Treasury | The contract that mints ZYR only against recorded pesos ([ADR 0007](adr/0007-on-chain-treasury.md)). |
| AccountFactory, guardian | The contract that creates residents' smart accounts, and the backend key that may start an account recovery and relays payments the phone signed ([ADR 0010](adr/0010-smart-accounts-and-recovery.md), [0029](adr/0029-closed-loop-payments.md)). |
| Safe, owner, threshold | A Safe is an audited multi-signature contract (version 1.4.1 here). Its owners are keys; a transaction runs only with signatures from at least the threshold of them. Zyrcle's admin Safe has three owners and a threshold of two ([ADR 0040](adr/0040-keys-guardian-and-multisig.md)). |
| Proposal | A JSON file with one Safe transaction, its EIP-712 data and the Safe's hash for it. `zyrcle-api safe propose` writes it, owners add signatures, `safe exec` sends it. |
| Outbox | A table that a database transaction writes to. A worker sends its rows to the outside world. |
| Sentry | A hosted error-report service ([ADR 0033](adr/0033-error-reports-and-uptime.md)). |
| age, R2 | `age` is a file encryption tool with public and private keys. Cloudflare R2 is an S3-compatible storage bucket service. Together they make the off-site backups ([ADR 0034](adr/0034-encrypted-off-site-backups.md)). |
| Playwright | A tool that drives a real browser for the end-to-end tests ([ADR 0031](adr/0031-testing-and-the-pre-production-check.md)). |

## 2. Deployment diagram

Mermaid cannot draw one container inside two networks. The arrow labels name the network each
connection uses.

```mermaid
flowchart TB
  users(["Browsers and phones"])
  peers(["Fuji network peers"])

  subgraph vps["VPS aitera-vps: one host, Docker"]
    traefik["Traefik reverse proxy<br/>entrypoint websecure, TLS resolver le<br/>configuration not in this repository"]
    subgraph app["Compose project zyrcle: deploy/compose.yml"]
      web["web<br/>nginx-unprivileged, port 8080"]
      api["api<br/>FastAPI and background workers, port 8000"]
      migrate["migrate, profile ops<br/>alembic upgrade head"]
      pg[("postgres 17<br/>volume pgdata")]
      mq["mosquitto 2.1.4<br/>port 1883, no TLS"]
      sim["sim<br/>simulated containers ctr-0001 to ctr-0004<br/>control port 8090, volume sim-keys"]
    end
    subgraph l1["Compose project zyrcle-l1: infra/l1/node"]
      l1node["node: AvalancheGo v1.15.3 with Subnet-EVM<br/>ZyrcleChain validator<br/>HTTP 9650, P2P 9651, volume node-data"]
    end
    keys["Host key files<br/>~/.avalanche-cli/key/"]
    backups[("Host folder ~/backups/zyrcle<br/>daily dump, cron 03:15 UTC, 14 days")]
  end

  users -->|"HTTPS zyrcle.deviego.xyz"| traefik
  users -->|"HTTPS and WSS zyrcle-backend.deviego.xyz"| traefik
  users -->|"HTTPS rpc.zyrcle.deviego.xyz, /rpc and /ws only"| traefik
  traefik -->|"edge"| web
  traefik -->|"edge, rate limit 20/s, burst 60"| api
  traefik -->|"edge, rate limit 20/s, burst 40"| l1node
  api -->|"internal: SQL"| pg
  migrate -->|"internal: SQL"| pg
  api <-->|"internal: MQTT"| mq
  sim <-->|"internal: MQTT"| mq
  api -->|"internal: HTTP demo control"| sim
  api -->|"edge: JSON-RPC and /ext/health on zyrcle-l1-node-1:9650"| l1node
  keys -.->|"oracle.key, operator.key, guardian.key, read-only"| api
  peers <-->|"P2P 9651, published"| l1node
  pg -.->|"backup.sh: pg_dump"| backups
  backups -.->|"offsite.sh, age-encrypted<br/>not configured yet"| r2[("Cloudflare R2 bucket")]

  api -->|"HTTPS"| expo["Expo push service"]
  expo --> fcm["FCM for Android<br/>APNs for iOS"]
  fcm --> users
  api -->|"HTTPS"| resend["Resend email API"]
  api -->|"HTTPS, certificate copies"| pinata["Pinata IPFS API"]
  api -.->|"HTTPS, ticket photos<br/>off until a key is set"| anthropic["Anthropic API"]
  api -.->|"HTTPS, error reports"| sentry["Sentry"]

  gha["GitHub Actions<br/>CI and Release images"] -->|"push images"| ghcr[("GHCR<br/>ghcr.io/diegowritescode")]
  ghcr -.->|"docker pull in deploy.sh,<br/>then run by digest"| api
  ghcr -.->|"docker pull in deploy.sh,<br/>then run by digest"| web
  uptime["GitHub Actions<br/>Uptime, every 10 min"] -->|"HTTPS checks"| traefik
  eas["EAS Build, on Diego's Mac<br/>or on Expo's cloud"] -->|"APK or AAB"| users
```

### Networks

| Network | Defined in | What it is | Members |
|---|---|---|---|
| `internal` | [deploy/compose.yml](../deploy/compose.yml) | A bridge network that compose creates (`zyrcle_internal`). It is not marked `internal: true`, so its containers can still reach the internet. | postgres, mosquitto, migrate, api, sim |
| `edge` | Created outside this repository. Both compose files declare it `external`. | The network Traefik uses to reach containers. Diego's other projects run behind the same Traefik ([ADR 0020](adr/0020-single-vps-docker-compose.md)). | api, web, L1 node (Zyrcle's members) |
| `zyrcle-l1_default` | [infra/l1/node/compose.yml](../infra/l1/node/compose.yml) | The L1 project's default bridge network. | L1 node |

### Public endpoints

| Endpoint | Served by | Notes |
|---|---|---|
| `https://zyrcle.deviego.xyz` | `web` | The web app, dashboards and the operator console (`/console`). |
| `https://zyrcle-backend.deviego.xyz` | `api` | REST and WebSocket. Rate limited by Traefik. |
| `https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc` (and `/ws`) | L1 node | Only these two paths are routed. The node's info, admin and P-Chain APIs return 404 from outside ([infra/l1/README.md](../infra/l1/README.md)). |
| VPS port 9651 | L1 node | The validator's peer-to-peer port. Fuji peers must reach it. |

## 3. Environments

### 3.1 Production

- **Host.** One VPS, reached with `ssh aitera-vps`. The deploy user is `diego`. The repository is
  checked out at `~/apps/zyrcle` ([deploy/README.md](../deploy/README.md)). ADR 0002 sizes the VPS at
  2 cores and 4 GB of RAM.
- **Two compose projects.** `zyrcle` ([deploy/compose.yml](../deploy/compose.yml)) holds the
  application. `zyrcle-l1` ([infra/l1/node/compose.yml](../infra/l1/node/compose.yml)) holds the
  validator. `deploy/deploy.sh` never touches the L1 project.
- **Domains** ([ADR 0020](adr/0020-single-vps-docker-compose.md)): `zyrcle.deviego.xyz` (web),
  `zyrcle-backend.deviego.xyz` (API), `rpc.zyrcle.deviego.xyz` (public RPC). Email goes out as
  `no-reply@zyrcle.deviego.xyz`.
- **Chain.** ZyrcleChain v2 on the Fuji testnet. ZYR has no real value there. The Treasury's seed
  capital is simulated ([ADR 0023](adr/0023-testnet-economics.md)). Since 2026-11-23 a 2-of-3 Safe
  holds every admin power of the chain ([section 7](#7-zyrclechain), runbook 9.14).
- **Secrets.** `deploy/.env` exists only on the VPS. Private keys are files in
  `~/.avalanche-cli/key/` on the VPS ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)).
  The admin Safe's owners sign from Diego's wallets and a paper key (section 6.1).
- **Deployed version.** The images of commit `0d41852`, run by digest since 2026-11-26 05:36 UTC;
  the database is at migration 0017 (since 00:55 UTC the same day). `deploy/history.log` on the VPS records every deploy
  (section 8.3).
- **Backups.** `deploy/backup.sh` runs from cron at 03:15 UTC into `~/backups/zyrcle`
  (runbook 9.10).
- **External services on 2026-11-23**, as reported that day; the repository cannot show which keys
  `deploy/.env` holds.

  | Service | State |
  |---|---|
  | Resend (email), Pinata (IPFS copies), Expo push, the uptime workflow | on |
  | Sentry (error reports), in the API and the web app since 2026-11-26; in the app from the APK built that day | on |
  | The off-site bucket, Anthropic (ticket reading) | off until Diego opens the accounts and places the keys |

- **No staging environment** is in the repository.

### 3.2 Local development

[repository.md](repository.md), [apps/api/README.md](../apps/api/README.md) and
[apps/web/README.md](../apps/web/README.md) give the full steps. In short:

- **Postgres and Mosquitto** come from [apps/api/dev/compose.yml](../apps/api/dev/compose.yml)
  (project `zyrcle-dev`). Postgres 17 listens on `127.0.0.1:5432` with user, password and database
  all `zyrcle`. Mosquitto (`eclipse-mosquitto:2`) listens on `127.0.0.1:1883` with the same ACL as
  production. `dev/mosquitto/make-passwd.sh` creates the users `api` and `ctr-0001` to `ctr-0004`,
  all with the password `dev-password`.
- **The chain is anvil.** `anvil --chain-id 20261121` stands in for ZyrcleChain.
  [apps/api/dev/local_chain.py](../apps/api/dev/local_chain.py) installs a NativeMinter mock, deploys
  the Treasury, records 1,000,000 COP of seed capital and deploys the AccountFactory with the oracle
  as guardian. It writes anvil's well-known keys to `apps/api/dev/.local/oracle.key` and
  `operator.key`, and prints the `ZYRCLE_*` lines for `apps/api/.env`, including
  `ZYRCLE_EMAIL_LOG_ONLY=true` (emails go to the log).
- **The apps.** The simulator and the API run from the virtualenv. The web app runs with
  `npm run dev` on port 8080 and reads `apps/web/.env`. The mobile app runs with `npx expo start`;
  its defaults point at production unless `EXPO_PUBLIC_*` variables say otherwise.
- **Optional local L1.** `infra/l1/genesis.local.json` runs ZyrcleChain on an Avalanche CLI local
  network, with the public ewoq test key as admin. It was verified on 2026-11-21
  ([infra/l1/README.md](../infra/l1/README.md)).

```bash
cd apps/api && docker compose -f dev/compose.yml up -d && .venv/bin/alembic upgrade head
anvil --chain-id 20261121 &
.venv/bin/python dev/local_chain.py >> .env
ZYRCLE_SIM_PASSWORD=dev-password .venv/bin/zyrcle-sim serve --keys-dir dev/.local/keys \
  --devices ctr-0001,ctr-0002,ctr-0003,ctr-0004 --control-host 127.0.0.1 &
.venv/bin/zyrcle-api demo seed --keys-dir dev/.local/keys --devices ctr-0001,ctr-0002,ctr-0003,ctr-0004
.venv/bin/zyrcle-api serve &
cd ../web && npm ci && cp .env.example .env && npm run dev
```

### 3.3 Tests and CI

CI runs on GitHub-hosted Ubuntu runners (`ubuntu-latest`, except the end-to-end job on
`ubuntu-24.04`, because Playwright 1.57 has no Chromium build for the newer image) with Python 3.13
and Node 22. The `api` and `e2e` jobs start services:

- **Postgres** `postgres:17-alpine` as a job service on port 5432 (user, password and database
  `zyrcle`).
- **Mosquitto** `eclipse-mosquitto:2`, started with `docker run`, using the development
  configuration, ACL and password file.
- **anvil** from Foundry v1.5.1. The pytest fixture starts it on a free port with chain ID
  20261121. Chain tests skip when anvil is missing.
- **The whole stack, end to end** (`e2e` only, [e2e/README.md](../e2e/README.md)):
  `e2e/stack/up.sh` starts anvil on 8546, a fresh database, the simulator, the API on 8010 and
  stand-ins for Pinata, the IPFS gateway and Anthropic (`fake-services.mjs`, port 8093);
  `e2e/stack/apps.sh` builds the web app and the mobile app's web export against it. Playwright
  then walks every party's journey in Chromium, the Safe's signing included.

Tests read `ZYRCLE_TEST_DATABASE_URL` and `ZYRCLE_TEST_MQTT_HOST` to point elsewhere. CI never
deploys. [Section 8](#8-cicd) lists every job.

## 4. Production services

### 4.1 Settings shared by the services

- **Images by digest.** `api`, `migrate` and `sim` run `${ZYRCLE_API_IMAGE}`; `web` runs
  `${ZYRCLE_WEB_IMAGE}`. `deploy.sh` pulls `ghcr.io/diegowritescode/zyrcle-api:<sha>` and
  `zyrcle-web:<sha>` by their full commit SHA, reads their digests and writes both variables as
  `repository@sha256:…` into `deploy/.env`. Compose refuses to start without them. `deploy.sh`
  rejects any tag that is not 40 hexadecimal characters, and `latest` is never used
  ([ADR 0020](adr/0020-single-vps-docker-compose.md),
  [ADR 0032](adr/0032-deploys-pinned-recorded-and-backed-up.md)). `ZYRCLE_API_TAG` is still written
  and names the release in error reports.
- **Third-party images by digest.** `postgres:17-alpine` and `eclipse-mosquitto:2.1.4-alpine` in
  compose, and the base images `python:3.13-slim`, `node:22-alpine` and
  `nginxinc/nginx-unprivileged:1.29-alpine`, carry an `@sha256:` digest. Dependabot opens weekly
  pull requests for the Dockerfiles in `apps/api`, `apps/web` and `infra/l1/node` and for
  `deploy/compose.yml`, and monthly ones for GitHub Actions; each runs the whole CI.
- **Logging.** The `x-logging` anchor keeps Docker's JSON log files at 10 MB, three files per
  container. `migrate` does not use it.
- **Hardening.** The `x-hardened` anchor sets a read-only root filesystem, a `tmpfs` at `/tmp`, drops
  every Linux capability and sets `no-new-privileges`. `mosquitto`, `api`, `sim` and `web` use it.
  `postgres` and `migrate` do not.
- **Restart policy.** Every long-running service has `restart: unless-stopped`.
- **The backend image** ([apps/api/Dockerfile](../apps/api/Dockerfile)) builds in two stages from
  `python:3.13-slim` (pinned by digest). It installs `packages/protocol`,
  `device/simulator[control]` and `apps/api` into a virtualenv, copies `alembic.ini` and the
  migrations, and runs as user `zyrcle` (UID 10001). Its default command is `zyrcle-api serve
  --host 0.0.0.0 --port 8000`. The same image runs the simulator.
- **The web image** ([apps/web/Dockerfile](../apps/web/Dockerfile)) builds the Vite app with
  `node:22-alpine` and serves it with `nginxinc/nginx-unprivileged:1.29-alpine` on port 8080, both
  pinned by digest. The `VITE_*` values are baked in at build time
  ([section 5.4](#54-web-and-mobile-build-time-settings)).

### 4.2 Each service

**postgres**
- Image `postgres:17-alpine`, pinned by digest. Default command. No published port.
- Volume `pgdata` at `/var/lib/postgresql/data`. Network `internal`.
- Health check `pg_isready -U zyrcle -d zyrcle` every 10 s, 5 retries.
- Memory limit 384 MB. Not hardened.

**mosquitto**
- Image `eclipse-mosquitto:2.1.4-alpine`, pinned by digest. Entrypoint
  `/usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf`.
- Runs as `${DEPLOY_UID}:${DEPLOY_GID}`. Without capabilities it cannot drop root by itself, and its
  password and ACL files can stay `0600`.
- Read-only bind mounts from `deploy/mosquitto/`: `mosquitto.conf`, `acl.runtime` (as `acl`) and
  `passwd`. `deploy.sh` generates the last two; git ignores them.
- [mosquitto.conf](../deploy/mosquitto/mosquitto.conf): one plain listener on 1883, no anonymous
  users, no persistence, logs to stdout. No TLS.
- [ACL](../deploy/mosquitto/acl): user `api` reads every device's uplink (also through the shared
  subscription `$share/zyrcle-api/...`) and writes every device's commands. Any other user is a
  device: it may publish only its own uplink and read only its own commands.
- Network `internal`. No health check. Memory limit 64 MB. Hardened.

**migrate** (profile `ops`, run on demand)
- Backend image. Command `alembic upgrade head`. Same environment as `api`.
- Waits for `postgres` to be healthy. Network `internal`.
- Runs as the image user (`zyrcle`). Not hardened. No memory limit.

**api**
- Backend image, default command. Port 8000 is reached only through Traefik.
- Runs as `${DEPLOY_UID}:${DEPLOY_GID}`, so it can read the key files, which stay `0600` files of
  that user.
- Mounts `${ORACLE_KEY_PATH}` at `/run/secrets/oracle.key`, `${OPERATOR_KEY_PATH}` at
  `/run/secrets/operator.key` and `${GUARDIAN_KEY_PATH}` at `/run/secrets/guardian.key`, all
  read-only. `GUARDIAN_KEY_PATH` points at the oracle key file until runbook 9.13 runs.
- `ZYRCLE_DOCS_ENABLED=false`: no interactive API docs in production
  ([ADR 0028](adr/0028-pilot-readiness.md)).
- Waits for `postgres` (healthy) and `mosquitto` (started). Networks `internal` and `edge`.
- Health check: an HTTP GET of `http://127.0.0.1:8000/health` every 15 s, 5 retries, 20 s start
  period. `/health` runs `select 1` on the database and reports whether MQTT is connected. It
  answers `ok` even when MQTT is down.
- Memory limit 384 MB. Hardened.
- Traefik labels: router `zyrcle-api` on `Host(${API_HOST})`, entrypoint `websecure`, certificate
  resolver `le`, rate limit of 20 requests per second on average with bursts of 60.
- Uvicorn trusts forwarded headers from any address (`forwarded_allow_ips="*"`).
- One process serves HTTP and runs the background workers
  ([main.py](../apps/api/src/zyrcle_api/main.py)). Settings decide which workers start:

  | Worker | Starts when |
  |---|---|
  | MQTT bridge, session sweep, collection sweep, QR code rotation | always |
  | Push notifications | `ZYRCLE_PUSH_ENABLED` (default on) |
  | Payouts (advances) | RPC URL, Treasury address and oracle key are all set |
  | Settlements (sales), certificate anchors | the above plus the operator key; anchors pin a copy on IPFS when `ZYRCLE_PINATA_JWT` is set |
  | Relays (signed payments), recoveries | payouts' conditions plus the AccountFactory address; both use the guardian key |
  | Emails, health alerts | a Resend key is set, or log-only mode |

  Ticket reading is not a worker: with `ZYRCLE_ANTHROPIC_API_KEY` set, the API calls Claude when an
  operator uploads a ticket photo ([ADR 0038](adr/0038-reading-scale-tickets-with-ai.md)).
  Rate limits run as middleware unless `ZYRCLE_RATE_LIMITS_ENABLED` is false
  ([ADR 0035](adr/0035-rate-limits.md)).

**sim**
- Backend image. Command `zyrcle-sim serve --broker mosquitto --keys-dir /keys --devices ctr-0001,ctr-0002,ctr-0003,ctr-0004 --control-port 8090`.
- Volume `sim-keys` at `/keys`. It holds each simulated container's private key (created on first
  start) and its saved contents.
- Port 8090 (the control panel) is reachable only on `internal`. The API uses it for the `/v1/demo`
  routes.
- Waits for `mosquitto` (started). Runs as the image user. Memory limit 192 MB. Hardened.

**web**
- Web image, default command. Port 8080 is reached only through Traefik.
- `tmpfs` at `/tmp` and `/var/cache/nginx`. Network `edge`. No health check. Memory limit 64 MB.
  Hardened.
- Traefik labels: router `zyrcle-web` on `Host(${WEB_HOST})`, entrypoint `websecure`, resolver `le`.
  No rate limit.
- [nginx.conf](../apps/web/nginx.conf): files under `/assets/` are cached for a year; every other
  path falls back to `index.html` with `no-cache`.
- [security-headers.conf](../apps/web/security-headers.conf) sets `nosniff`, a strict referrer
  policy, `X-Frame-Options: DENY`, a permissions policy that allows only the camera for this
  origin, and this Content Security Policy:
  `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self' https://zyrcle-backend.deviego.xyz wss://zyrcle-backend.deviego.xyz https://rpc.zyrcle.deviego.xyz https://gateway.pinata.cloud https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://*.ingest.de.sentry.io; img-src 'self' data: https://images.unsplash.com; media-src 'self' data: blob: mediastream:; style-src 'self' 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.
  The production domains, the IPFS gateway (certificate copies) and Sentry's ingest hosts (error
  reports) are written into it. A domain change needs an edit here and a new image.

### 4.3 Start order

```
postgres (healthy) ─► backup.sh ─► migrate ─► sim (keys created) ─► demo seed ─► api, web
mosquitto (started) ─┘
```

`deploy.sh` enforces this order ([section 8.3](#83-deploy-procedure)). Compose itself only knows
that `api` needs `postgres` and `mosquitto`, `migrate` needs `postgres`, and `sim` needs
`mosquitto`. The API's use of the L1 node is not a compose dependency, because the node is another
project.

### 4.4 The L1 node (project `zyrcle-l1`)

- **Image.** Built on the VPS from [infra/l1/node/Dockerfile](../infra/l1/node/Dockerfile) as
  `zyrcle-l1-node:v1.15.3`. The base `avaplatform/subnet-evm:v1.15.3` is pinned by digest. The
  image runs as user `avalanche` (UID 10001) with entrypoint
  `./avalanchego --config-file=/config/node.json`. It is not published to GHCR.
- **Ports.** 9651 (P2P) on every interface. 9650 (HTTP API) on `127.0.0.1` only, for the CLI on the
  host.
- **Volumes.** `node-data` at `/data` holds the node identity: staking key, TLS certificate and BLS
  signer. Losing it means a new NodeID, which is no longer the validator. `node.json` and `chains/`
  are mounted read-only.
- **Configuration.** [node.json](../infra/l1/node/node.json): Fuji, partial sync of the primary
  network, admin API off, info and metrics APIs on, JSON logs, tracks subnet
  `YZ1nRuEqM6LGAJoQqEkyirLvQbfxps8LutUBKFPGaYRjYSjMN`. The chain config in
  `chains/<BlockchainID>/config.json` enables the `eth`, `eth-filter`, `net`, `web3` and `internal-*`
  APIs, pruning and the Warp API.
- **Limits.** Hardened like the application containers. Memory limit 3 GB with
  `GOMEMLIMIT=2560MiB`. Logs 20 MB, five files.
- **Networks.** Its default network and `edge`. Any container on `edge` can reach the whole HTTP
  API on port 9650, minus the admin API.
- **Public RPC.** The Traefik labels turn on only when `infra/l1/node/.env` sets
  `RPC_PUBLIC=true`. Router `zyrcle-rpc` matches `RPC_HOST` and the paths
  `/ext/bc/<BLOCKCHAIN_ID>/rpc` and `/ws`. Rate limit 20 requests per second, bursts of 40.
- No health check in compose.

### 4.5 Memory budget

| Container | Limit |
|---|---|
| L1 node | 3,072 MiB |
| postgres | 384 MiB |
| api | 384 MiB |
| sim | 192 MiB |
| mosquitto | 64 MiB |
| web | 64 MiB |
| **Total** | **4,160 MiB** |

The limits add up to more than the 4 GB of RAM in ADR 0002. Limits are ceilings, not reservations.
Traefik and the VPS's other projects come on top.

## 5. Configuration

No real secret value appears in this document or anywhere in the repository. Example values below
are public: addresses, IDs and domains.

### 5.1 API settings (`ZYRCLE_*`)

`Settings` in [config.py](../apps/api/src/zyrcle_api/config.py) reads environment variables with the
prefix `ZYRCLE_`, then a `.env` file in the working directory (locally `apps/api/.env`; the image
has none). Unknown variables are ignored. "Default" means the column is not set in
[deploy/compose.yml](../deploy/compose.yml).

| Variable | Default | Production | Secret | What it does |
|---|---|---|---|---|
| `ZYRCLE_DATABASE_URL` | `postgresql+asyncpg://zyrcle:zyrcle@localhost:5432/zyrcle` | `postgresql+asyncpg://zyrcle:${POSTGRES_PASSWORD}@postgres:5432/zyrcle` | yes, it holds the password | Postgres connection. Alembic reads the same variable. |
| `ZYRCLE_MQTT_HOST` | `localhost` | `mosquitto` | no | Broker host. |
| `ZYRCLE_MQTT_PORT` | `1883` | default | no | Broker port. |
| `ZYRCLE_MQTT_USERNAME` | `api` | `api` | no | Broker user. The ACL gives `api` every device's topics. |
| `ZYRCLE_MQTT_PASSWORD` | empty | `${MQTT_API_PASSWORD}` | yes | Broker password. |
| `ZYRCLE_MQTT_SHARE_GROUP` | `zyrcle-api` | default | no | Shared-subscription group, so several API replicas split device traffic. Must match the ACL. |
| `ZYRCLE_JWT_SECRET` | none, required, at least 32 characters | `${JWT_SECRET}` | yes | Signs resident and operator sessions (HS256). Also keys the HMAC of emailed codes. |
| `ZYRCLE_JWT_TTL_MINUTES` | `1440` | default | no | Resident session length (24 h). |
| `ZYRCLE_OPERATOR_JWT_TTL_MINUTES` | `480` | default | no | Operator session length (8 h, [ADR 0014](adr/0014-operator-accounts.md)). |
| `ZYRCLE_OPERATOR_TOKEN` | none, required, at least 24 characters | `${OPERATOR_TOKEN}` | yes | Shared machine token for `/v1/operator/*`. It acts as an admin named `token`. |
| `ZYRCLE_SIWE_DOMAIN` | `zyrcle.deviego.xyz` | `${WEB_HOST}` | no | Domain that a Sign-In with Ethereum (SIWE) message must name. |
| `ZYRCLE_TIMEZONE` | `America/Bogota` | default | no | Local day for dashboards and turns. |
| `ZYRCLE_CHAIN_ID` | `20261121` | default | no | Chain ID that a SIWE message must name. |
| `ZYRCLE_CODE_ROTATION_S` | `30` | default | no | A container's QR code changes this often; each code lives twice as long. |
| `ZYRCLE_DEVICE_OFFLINE_AFTER_S` | `90` | default | no | A container with no message for this long counts as offline. |
| `ZYRCLE_UNLOCK_ACK_TIMEOUT_S` | `15` | default | no | How long a session waits for the container to confirm it opened. |
| `ZYRCLE_IDLE_TIMEOUT_S` | `60` | default | no | A deposit with no activity for this long is closed. |
| `ZYRCLE_COLLECTION_IDLE_TIMEOUT_S` | `600` | default | no | The same for a collection ([ADR 0012](adr/0012-collection-and-bags.md)). |
| `ZYRCLE_MEASUREMENT_TIMEOUT_S` | `20` | default | no | How long a closing session waits for the final measurement. |
| `ZYRCLE_SWEEP_INTERVAL_S` | `1.0` | default | no | How often the timeout sweepers run. |
| `ZYRCLE_FILL_SENSOR_NOISE_MM` | `2` | default | no | Distance sensor noise, used to bound the volume estimate. |
| `ZYRCLE_WEIGHT_CHANGE_G` | `10` | default | no | A weight change this large means material moved. |
| `ZYRCLE_CHAIN_RPC_URL` | none | `http://zyrcle-l1-node-1:9650/ext/bc/${BLOCKCHAIN_ID}/rpc` | no | ZyrcleChain JSON-RPC endpoint, reached over `edge`. |
| `ZYRCLE_TREASURY_ADDRESS` | none | `${TREASURY}` | no | Treasury contract address. |
| `ZYRCLE_ORACLE_KEY_FILE` | none | `/run/secrets/oracle.key` | the file is | Path to the hex private key with the Treasury's ORACLE_ROLE. |
| `ZYRCLE_ANTHROPIC_API_KEY` | none | `${ANTHROPIC_API_KEY:-}` | yes | Reads scale tickets from photos with Claude ([ADR 0038](adr/0038-reading-scale-tickets-with-ai.md)). Empty: off. `ZYRCLE_TICKET_MODEL` defaults to `claude-opus-5-5`; `ZYRCLE_ANTHROPIC_BASE_URL` is for tests only. |
| `ZYRCLE_RATE_LIMITS_ENABLED`, `ZYRCLE_RATE_LIMIT_CODES_PER_MIN` (20), `_SIGNIN_PER_MIN` (120), `_WRITE_PER_MIN` (120), `_READ_PER_MIN` (600), `_PROXY_HOPS` (1) | as listed | default | no | Rate limits per caller ([ADR 0035](adr/0035-rate-limits.md)). `PROXY_HOPS` is the number of proxies in front of the API: Traefik, one. |
| `ZYRCLE_SENTRY_DSN` | none | `${SENTRY_DSN_API:-}` | no | Sentry DSN of the API's project. Empty: no error reports ([ADR 0033](adr/0033-error-reports-and-uptime.md)). `ZYRCLE_SENTRY_ENVIRONMENT` (`production`) and `ZYRCLE_SENTRY_TRACES_SAMPLE_RATE` (`0.0`) keep their defaults. |
| `ZYRCLE_RELEASE` | none | `${ZYRCLE_API_TAG:-}` | no | The deployed commit, named in error reports. |
| `ZYRCLE_DOCS_ENABLED` | `true` | `"false"` | no | Interactive API docs (`/docs`, `/redoc`, `/openapi.json`) ([ADR 0028](adr/0028-pilot-readiness.md)). |
| `ZYRCLE_PRIVACY_VERSION`, `ZYRCLE_REQUIRE_CONSENT` | `2026-11-22`, `false` | default | no | The data-processing policy in force, and whether depositing requires having accepted it. Off until the pilot (ADR 0028). |
| `ZYRCLE_ALERT_INTERVAL_S` (600), `_ALERT_GAS_MIN_ZYR` (1.0), `_ALERT_AVAILABLE_MIN_COP` (100000), `_ALERT_STUCK_AFTER_MIN` (30), `_ALERT_CHAIN_STALE_MIN` (10) | as listed | default | no | Health report thresholds and how often the alert worker checks (runbook 9.11). |
| `ZYRCLE_CHAIN_HEALTH_URL` | none | `http://zyrcle-l1-node-1:9650/ext/health` | no | The validator node's health endpoint, checked by the health report ([ADR 0028, amendment](adr/0028-pilot-readiness.md#amendments)). Unset: not checked. |
| `ZYRCLE_OPERATOR_KEY_FILE` | none | `/run/secrets/operator.key` | the file is | Path to the hex private key with the Treasury's OPERATOR_ROLE. Without it, confirmed sales wait. |
| `ZYRCLE_SETTLEMENT_INTERVAL_S` | `3.0` | default | no | Settlement and anchor worker interval. |
| `ZYRCLE_RELAY_INTERVAL_S` | `2.0` | default | no | Relay worker interval (signed payments, [ADR 0029](adr/0029-closed-loop-payments.md)). |
| `ZYRCLE_ADVANCE_RATIO_BPS` | `5000` | default | no | Advance as a share of the reference price, in basis points (50 %, [ADR 0023](adr/0023-testnet-economics.md)). |
| `ZYRCLE_MAX_ADVANCE_COP` | `5000` | default | no | Advance cap per deposit, as in the contract. |
| `ZYRCLE_FILL_ALERT_PCT` | `80` | default | no | A container at or above this fill level pushes its host's collectors, once per fill cycle ([ADR 0042](adr/0042-collector-fill-alerts-and-earnings.md)). |
| `ZYRCLE_PAYOUT_INTERVAL_S` | `2.0` | default | no | Payout worker interval. |
| `ZYRCLE_PUSH_ENABLED` | `true` | default | no | Turns the push notification worker on. |
| `ZYRCLE_EXPO_PUSH_URL` | `https://exp.host/--/api/v2/push` | default | no | Expo push API base URL. |
| `ZYRCLE_EXPO_ACCESS_TOKEN` | none | `${EXPO_ACCESS_TOKEN:-}` | yes | Needed only if "enhanced security for push notifications" is on in Expo ([ADR 0008](adr/0008-push-notifications.md)). |
| `ZYRCLE_NOTIFICATION_INTERVAL_S` | `2.0` | default | no | Push worker interval. |
| `ZYRCLE_PUSH_RECEIPT_DELAY_S` | `900` | default | no | When to ask Expo for delivery receipts (15 min). |
| `ZYRCLE_ACCOUNT_FACTORY_ADDRESS` | none | `${ACCOUNT_FACTORY:-}` | no | AccountFactory address. Empty turns smart accounts and recovery off ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). |
| `ZYRCLE_GUARDIAN_KEY_FILE` | none, falls back to the oracle key | `/run/secrets/guardian.key`, from `GUARDIAN_KEY_PATH` | the file is | The AccountFactory guardian: starts and cancels recoveries, relays signed payments. `GUARDIAN_KEY_PATH` points at the oracle key until runbook 9.13 ([ADR 0040](adr/0040-keys-guardian-and-multisig.md)). |
| `ZYRCLE_RECOVERY_INTERVAL_S` | `5.0` | default | no | Recovery worker interval. |
| `ZYRCLE_RESEND_API_KEY` | none | `${RESEND_API_KEY:-}` | yes | Resend key. Without it, no email: no codes, no recovery, no operator sign-in. |
| `ZYRCLE_RESEND_API_URL` | `https://api.resend.com` | default | no | Resend API base URL. |
| `ZYRCLE_EMAIL_FROM` | `Zyrcle <no-reply@zyrcle.deviego.xyz>` | `${EMAIL_FROM:-Zyrcle <no-reply@zyrcle.deviego.xyz>}` | no | Sender address. |
| `ZYRCLE_PINATA_JWT` | none | `${PINATA_JWT:-}` | yes | Pinata JWT. With it, each impact certificate is pinned on IPFS before anchoring and its CID goes on chain; without it, certificates are anchored without a copy ([ADR 0027, amendment](adr/0027-impact-certificates.md#amendments)). |
| `ZYRCLE_PINATA_API_URL` | `https://api.pinata.cloud` | default | no | Pinata API base URL. |
| `ZYRCLE_IPFS_GATEWAY` | `https://gateway.pinata.cloud/ipfs/` | default | no | Where browsers read the copy (`ipfs_url`). Change it together with the web image's `VITE_IPFS_GATEWAY` and the `connect-src` of `apps/web/security-headers.conf`. |
| `ZYRCLE_EMAIL_INTERVAL_S` | `1.0` | default | no | Email worker interval. |
| `ZYRCLE_EMAIL_LOG_ONLY` | `false` | not set | no | Local development only: write emails to the log. |
| `ZYRCLE_CORS_ORIGINS` | empty | `https://${WEB_HOST}` | no | Comma-separated browser origins allowed to call the API. |
| `ZYRCLE_DEMO_SIMULATOR_URL` | none | `http://sim:8090` | no | Simulator control panel. Empty turns the `/v1/demo` routes off. |

Derived switches in `config.py`: payouts need the RPC URL, the Treasury address and the oracle key.
Sales also need the operator key. Accounts also need the factory address. Recovery needs accounts
and email. The IPFS copy needs the Pinata JWT.

### 5.2 `deploy/.env`

`deploy.sh` creates `deploy/.env` from [deploy/.env.example](../deploy/.env.example) the first time,
with fresh secrets. Of the variables added to `.env.example` later, it adds only
`ZYRCLE_API_IMAGE`, `ZYRCLE_WEB_IMAGE` and `GUARDIAN_KEY_PATH` to an existing file; add the others
by hand. The header of `.env.example` says "Generated by bootstrap.sh"; the script is `deploy.sh`.

| Variable | Value in `.env.example` or how it is set | Secret | Used for |
|---|---|---|---|
| `ZYRCLE_API_TAG` | written by every `deploy.sh` run | no | Backend image tag (full SHA); also `ZYRCLE_RELEASE`. |
| `ZYRCLE_WEB_TAG` | written by every `deploy.sh` run | no | Web image tag (full SHA). |
| `ZYRCLE_API_IMAGE`, `ZYRCLE_WEB_IMAGE` | written by every `deploy.sh` run, added if missing | no | The same images as `repository@sha256:…`; compose runs these. |
| `API_HOST` | `zyrcle-backend.deviego.xyz` | no | Traefik rule for `api`. |
| `WEB_HOST` | `zyrcle.deviego.xyz` | no | Traefik rule for `web`, SIWE domain, CORS origin. |
| `BLOCKCHAIN_ID` | `hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8` | no | Builds the RPC URL. |
| `TREASURY` | `0xd7052201140224018b123ecFF7b83B4251790Aeb` | no | Treasury address. |
| `ORACLE_KEY_PATH` | `$HOME/.avalanche-cli/key/zyrcle-oracle.pk` (set by `deploy.sh`) | path only | Host file mounted as the oracle key. |
| `OPERATOR_KEY_PATH` | `$HOME/.avalanche-cli/key/zyrcle-operator.pk` (set by `deploy.sh`) | path only | Host file mounted as the operator key ([ADR 0013](adr/0013-sale-and-settlement.md)). |
| `GUARDIAN_KEY_PATH` | the oracle key's path, set by `deploy.sh` on the first run or added if missing (`.env.example` shows the future `zyrcle-guardian.pk`) | path only | Host file mounted as the guardian key ([ADR 0040](adr/0040-keys-guardian-and-multisig.md), runbook 9.13). |
| `DEPLOY_UID`, `DEPLOY_GID` | `id -u`, `id -g` of the deploy user | no | User for `api` and `mosquitto`. |
| `POSTGRES_PASSWORD` | `token_urlsafe(32)` | yes | Database password. |
| `JWT_SECRET` | `token_urlsafe(48)` | yes | `ZYRCLE_JWT_SECRET`. |
| `OPERATOR_TOKEN` | `token_urlsafe(32)` | yes | `ZYRCLE_OPERATOR_TOKEN`. |
| `MQTT_API_PASSWORD` | `token_urlsafe(24)` | yes | Broker password of `api`. |
| `MQTT_CTR_0001_PASSWORD` to `MQTT_CTR_0004_PASSWORD` | `token_urlsafe(24)` each | yes | Broker passwords of the simulated containers. |
| `EXPO_ACCESS_TOKEN` | commented out | yes | Optional, [ADR 0008](adr/0008-push-notifications.md). |
| `ACCOUNT_FACTORY` | commented out | no | Optional, from `zyrcle-api chain accounts-deploy` ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). |
| `RESEND_API_KEY` | commented out | yes | Optional; needed for email, recovery and operator sign-in. Diego places it himself ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)). |
| `EMAIL_FROM` | commented out | no | Optional sender. |
| `PINATA_JWT` | commented out | yes | Optional; the IPFS copy of impact certificates. Only the JWT, scoped to pinning; Pinata's API key and secret are not used. Diego places it himself ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)). |
| `SENTRY_DSN_API` | commented out | no | Optional; the Sentry DSN of the API's project ([ADR 0033](adr/0033-error-reports-and-uptime.md)). |
| `OFFSITE_AGE_RECIPIENT`, `OFFSITE_S3_ENDPOINT`, `OFFSITE_S3_BUCKET`, `OFFSITE_S3_ACCESS_KEY_ID`, `OFFSITE_S3_SECRET_ACCESS_KEY` | commented out | the last two are | Optional; read by `deploy/offsite.sh`, not by compose. The age public key and the bucket ([ADR 0034](adr/0034-encrypted-off-site-backups.md)). Without all five the script does nothing. |
| `ANTHROPIC_API_KEY` | commented out | yes | Optional; ticket reading ([ADR 0038](adr/0038-reading-scale-tickets-with-ai.md)). An Anthropic key with a monthly spending limit. |

`deploy.sh` also renames two legacy names in place: `ZYRCLE_DEMO_TAG` becomes `ZYRCLE_WEB_TAG` and
`DEMO_HOST` becomes `WEB_HOST`.

### 5.3 Other variables

| Variable | Where | Secret | What it does |
|---|---|---|---|
| `ZYRCLE_SIM_PASSWORD_<DEVICE>` (for example `ZYRCLE_SIM_PASSWORD_CTR_0001`), fallback `ZYRCLE_SIM_PASSWORD` | simulator | yes | Broker password per simulated container. |
| `SKIP_PULL=1` | `deploy.sh` | no | Skips the pulls and uses images already on the machine, for example after pulling them by hand (runbook 9.1). |
| `DEPLOY_ANY_CHECKOUT=1` | `deploy.sh` | no | Allows a checkout other than the API's commit, to roll back only the web app (runbook 9.2). |
| `BACKUP_DIR`, `BACKUP_KEEP_DAYS` | `backup.sh`; `offsite.sh` reads `BACKUP_DIR` too | no | Dump folder (default `~/backups/zyrcle`) and retention (default 14 days). |
| `OFFSITE_KEYS_DIR`, `OFFSITE_NODE_VOLUME`, `OFFSITE_S3_PROVIDER`, `OFFSITE_DOCKER_NETWORK` | `offsite.sh` | no | Defaults `~/.avalanche-cli/key`, `zyrcle-l1_node-data`, `Cloudflare`, none. The self-test overrides them. |
| `RPC_PUBLIC`, `RPC_HOST`, `BLOCKCHAIN_ID` | `infra/l1/node/.env` (not committed) | no | Public RPC route. Defaults: `false`, `rpc.zyrcle.deviego.xyz`, `unset`. |
| `ZYRCLE_CHAIN_RPC_URL`, `ZYRCLE_TREASURY_ADDRESS`, `ZYRCLE_ACCOUNT_FACTORY_ADDRESS` | `zyrcle-api chain …`, `zyrcle-api safe …` | no | The chain and Safe commands read only these. The wrapper script sets all three from `infra/l1/fuji.env` (`BLOCKCHAIN_ID`, `TREASURY`, `ACCOUNT_FACTORY`). |
| `ADMIN_PRIVATE_KEY` or `ADMIN_ADDRESS`, `SMOKE_MINT` | `infra/l1/scripts/smoke-test.sh` | the key is | Full or read-only smoke test. `SMOKE_MINT=1` mints for real, local networks only. |
| `AVALANCHE_PRIVATE_KEY` | `platform-cli` | yes | Read from the key file in the shell, never typed as an argument. |
| `KEY_FILE`, `AVAX_URI` | `infra/l1/tools/import-atomic.mjs` | the file is | Finishes a stuck C-Chain to P-Chain transfer. |
| `ZYRCLE_TEST_DATABASE_URL`, `ZYRCLE_TEST_MQTT_HOST` | API tests | no | Point the tests at another database or broker. |
| `E2E_PG`, `E2E_PY`, `E2E_STATE` | `e2e/stack/*.sh` | no | Postgres URL, the API's Python folder and the state folder of the end-to-end stack ([e2e/README.md](../e2e/README.md)). |
| `ANVIL_RPC` | `apps/api/dev/local_chain.py` | no | anvil URL, default `http://127.0.0.1:8545`. |
| `GOOGLE_SERVICES_JSON` | EAS environment variable, type file, visibility secret; on the Mac, set by `build-apk.sh` to the local copy's full path | yes | Path to Firebase's `google-services.json`, read by [app.config.ts](../apps/mobile/app.config.ts). |
| `ZYRCLE_LOCAL_BUILD` | `apps/mobile/scripts/build-apk.sh` | no | `1` gives Gradle a 6 GB heap and two workers, for builds on the Mac ([ADR 0043](adr/0043-android-builds-on-the-mac.md)). |

### 5.4 Web and mobile build-time settings

Both clients bake their settings in at build time. A different deployment needs a new build.

| Web (`VITE_*`) | Mobile (`EXPO_PUBLIC_*`) | Production value | Must match |
|---|---|---|---|
| `VITE_API_URL` | `EXPO_PUBLIC_API_URL` | `https://zyrcle-backend.deviego.xyz` | `API_HOST` |
| `VITE_SIWE_DOMAIN` | `EXPO_PUBLIC_SIWE_DOMAIN` | `zyrcle.deviego.xyz` | `ZYRCLE_SIWE_DOMAIN` (`WEB_HOST`) |
| `VITE_CHAIN_ID` | `EXPO_PUBLIC_CHAIN_ID` | `20261121` | `ZYRCLE_CHAIN_ID` |
| `VITE_RPC_URL` | `EXPO_PUBLIC_RPC_URL` | the public RPC URL above | `BLOCKCHAIN_ID` |
| `VITE_TREASURY_ADDRESS` | none | `0xd7052201140224018b123ecFF7b83B4251790Aeb` | `TREASURY` |
| `VITE_IPFS_GATEWAY` | none | `https://gateway.pinata.cloud/ipfs/` | `ZYRCLE_IPFS_GATEWAY`, the `connect-src` of `security-headers.conf` |
| `VITE_SENTRY_DSN` | `EXPO_PUBLIC_SENTRY_DSN` | the DSN of the project `zyrcle-web` or `zyrcle-mobile` (set 2026-11-26) | repository variable `SENTRY_DSN_WEB` for the web image; EAS variable for the app, visibility sensitive so builds on the Mac can read it ([ADR 0033](adr/0033-error-reports-and-uptime.md)) |
| `VITE_RELEASE` | none | the commit SHA, passed by the release workflow | the image tag |
| none | `EXPO_PUBLIC_ACCOUNT_FACTORY` | `0x0bE806Ca77340aA50AF6586CDC2FE2561668DaEA` | `ACCOUNT_FACTORY`, `infra/l1/fuji.env` |
| none | `EXPO_PUBLIC_WEB_URL` | `https://zyrcle.deviego.xyz` | `WEB_HOST` |

The web production values are `ARG` defaults in [apps/web/Dockerfile](../apps/web/Dockerfile);
[apps/web/src/lib/config.ts](../apps/web/src/lib/config.ts) repeats them as fallbacks, except the
API URL, which falls back to `http://127.0.0.1:8000`. The release workflow passes only
`VITE_SENTRY_DSN` and `VITE_RELEASE`. [apps/web/.env.example](../apps/web/.env.example) holds local
values. The mobile production values are the fallbacks in
[apps/mobile/src/lib/config.ts](../apps/mobile/src/lib/config.ts).

## 6. Secrets and keys

This section lists names and locations only. The repository holds no secret values.

**Rules** ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)):

- Private keys live only on the VPS, in `~/.avalanche-cli/key/` as `0600` files owned by the deploy
  user, and in Diego's offline operations inventory. That inventory is never shown in chats or
  committed.
- Diego places API keys himself over SSH. They never pass through a chat.
- `deploy/.env` exists only on the VPS and is never printed.
- Pushing, deploying, deleting, running contract transactions on Fuji, installing software on the
  VPS and spending EAS builds on Expo's cloud all need Diego's explicit approval. A build on Diego's
  Mac spends nothing and needs none ([ADR 0043](adr/0043-android-builds-on-the-mac.md)).

### 6.1 On-chain keys

| Key | Location | Public address ([fuji.env](../infra/l1/fuji.env)) | What it controls | If it leaks |
|---|---|---|---|---|
| Admin Safe owners (three) | Diego's Core wallet, his phone's MetaMask, and a paper key kept apart from both | `0xEBf748F482367cDe60c53abBae3Bd4e130eD656F`, `0xA8a526391635612Ec250a78C8AaAdD8a78421646`, `0x8548277163d01F6225dD01BE740C86d286FD8C6F` (`SAFE_OWNERS`) | Any two of them sign for the Safe `0x607c011C6921eA75C1e38223a5E5514eDbA7E43b` (`SAFE`), which since 2026-11-23 holds every admin power: admin of the NativeMinter, ContractDeployerAllowList, FeeManager and RewardManager precompiles; owner of the validator manager and of its proxy admin; `DEFAULT_ADMIN_ROLE` of the Treasury and of the AccountFactory ([ADR 0040](adr/0040-keys-guardian-and-multisig.md), runbook 9.14). | One owner key alone can do nothing. Two can mint ZYR outside the Treasury's backing rule, change fees, allow any deployer, grant Treasury roles, replace the guardian and change the validator set. Losing two of the three locks these powers for good. A Safe owner can be replaced by a Safe transaction; the repository has no command or procedure for it. |
| L1 admin | `~/.avalanche-cli/key/zyrcle-l1-admin.pk` on the VPS | `0xfdDD10F3BB701dCB21bF711bf3d28f96FA9a2f7d` (`L1_ADMIN`) | No admin power since 2026-11-23: it is off every precompile and renounced its contract roles. It holds the rest of the genesis float (about 48 ZYR), which `chain fund` sends to the backend's keys for gas (runbook 9.12), and it pays the gas of `safe exec`. ADR 0040 moves it off the VPS once that float has another holder. | The holder can spend the float. It cannot mint, deploy contracts, change fees, roles or validators. |
| P-Chain key | `~/.avalanche-cli/key/zyrcle-pchain.pk` on the VPS | `P-fuji1n3qzgzxfxjk05qss6hjvgmhd94wa3tvsw0ygch` (`PCHAIN_OWNER`) | Signs P-Chain transactions with `platform-cli`: subnet, chain, conversion to L1, validator balance ([ADR 0021](adr/0021-l1-operations.md)). Holds the test AVAX that funds the validator. | The holder can spend its test AVAX. What else it controls after the L1 conversion is not in the repository. |
| Treasury operator | `~/.avalanche-cli/key/zyrcle-operator.pk`, mounted into `api` at `/run/secrets/operator.key` | `0x528815e03Aa80b045B32840f3e26B394D0838d0d` | `OPERATOR_ROLE`: `recordSeedCapital`, `recordSale`, `setAdvanceLimits`. The backend uses it only after a named operator confirms the bank match ([ADR 0013](adr/0013-sale-and-settlement.md)). | The holder can record fake sales or seed capital and back new ZYR with them. The Safe can revoke the role with one proposal (runbook 9.4); every sale carries its evidence hash, and the bank reconciliation would not match (ADR 0013). It can also raise the advance limits (`setAdvanceLimits` in [Treasury.sol](../chain/src/Treasury.sol)). |
| Treasury oracle, also the AccountFactory guardian | `~/.avalanche-cli/key/zyrcle-oracle.pk`, mounted into `api` at `/run/secrets/oracle.key` and, through `GUARDIAN_KEY_PATH`, at `/run/secrets/guardian.key` | `0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50` (`TREASURY_ORACLE`, `ACCOUNT_GUARDIAN`) | `ORACLE_ROLE`: `payAdvance`, `settleResidents`, `payCollector`, `payHost`. As guardian it starts and cancels recoveries and relays signed payments. It is on the ContractDeployerAllowList so it can deploy accounts. | It can pay at most the daily cap per resident address until the Safe pauses the Treasury; it cannot raise `backing` ([ADR 0007](adr/0007-on-chain-treasury.md)). It can start a recovery on any account, which takes effect after 48 hours unless the owner cancels ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). The Safe can replace the guardian with one proposal. ADR 0040 gives the guardian its own key; runbook 9.13 has not run yet. |
| Validator identity | Docker volume `zyrcle-l1_node-data` (`/data` in the node) | `NodeID-LEXURXpvabdwVCyUZeTUKLFPf2won5DXp` | Staking key, TLS certificate and BLS signer of the validator. | Losing it gives a new NodeID that is no longer the validator ([infra/l1/node/compose.yml](../infra/l1/node/compose.yml)). The repository does not discuss a leak. |
| Simulated container keys | Docker volume `zyrcle_sim-keys`, files `ctr-000N.pem` | none | Sign each simulated container's messages ([device-protocol.md](device-protocol.md)). | The holder can forge that container's readings, and so deposits and advances. Deleting the volume makes new keys; the next `deploy.sh` registers them (`demo seed` updates changed public keys). |

The oracle and operator keys pay gas in ZYR. They are funded with `chain fund` from the L1 admin's
genesis float (100 ZYR at genesis): about 5 ZYR each on 2026-11-22 and 20 more each on 2026-11-23
(runbook 9.12). After the handover the admin key held about 48 ZYR. Nothing funds them
automatically; see section 10.

### 6.2 Secrets in `deploy/.env`

| Secret | What it is for | If it leaks |
|---|---|---|
| `POSTGRES_PASSWORD` | The database user's password. Postgres is reachable only on `internal`. | Read and write every table, for someone who can reach the database. |
| `JWT_SECRET` | Signs resident and operator sessions; keys the HMAC of email codes ([operator_auth.py](../apps/api/src/zyrcle_api/operator_auth.py), [email_codes.py](../apps/api/src/zyrcle_api/email_codes.py)). | The holder can forge a session for any resident or operator, admins included. |
| `OPERATOR_TOKEN` | Shared machine token; acts as admin `token` ([ADR 0014](adr/0014-operator-accounts.md)). | Every operator action: add admins, approve deposits, record and confirm sales. A confirmed sale makes the backend record it on chain with the operator key. ADR 0014 says to rotate it once operators have their own accounts. |
| `MQTT_API_PASSWORD` | The API's broker account. | Read every device's uplink and send commands (`display`, `unlock`, `lock`) to any container. Commands are not signed ([device-protocol.md](device-protocol.md)). The broker is not published outside the VPS. |
| `MQTT_CTR_0001_PASSWORD` … `0004` | Each simulated container's broker account. | Publish on that container's topics. Messages still need the device's signature, so the password alone cannot forge readings. |
| `EXPO_ACCESS_TOKEN` (optional) | Expo push with enhanced security ([ADR 0008](adr/0008-push-notifications.md)). | Send push notifications through the project, when enhanced security is on. |
| `OFFSITE_S3_ACCESS_KEY_ID`, `OFFSITE_S3_SECRET_ACCESS_KEY` (optional) | Write the encrypted copies to the backup bucket ([ADR 0034](adr/0034-encrypted-off-site-backups.md)). | Read the copies, which are useless without Diego's private age key, and fill or try to delete them; the bucket lock keeps recent ones. |
| `ANTHROPIC_API_KEY` (optional) | Reads ticket photos with Claude ([ADR 0038](adr/0038-reading-scale-tickets-with-ai.md)). | Spend on Zyrcle's Anthropic account up to its monthly limit. |
| `RESEND_API_KEY` (optional) | Sends email for the verified domain. | Send email as `no-reply@zyrcle.deviego.xyz` and use up the daily quota ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). |
| `PINATA_JWT` (optional) | Pins impact certificates on IPFS ([ADR 0027, amendment](adr/0027-impact-certificates.md#amendments)). | Pin or, if the key allows it, unpin files in Zyrcle's Pinata account and use up its quota. It cannot change a pinned file: a CID is its content's hash. |

Files derived from these: `deploy/mosquitto/passwd` (hashed broker passwords) and
`deploy/mosquitto/acl.runtime`. Both are `0600` and ignored by git.

### 6.3 External accounts and credentials

| Credential | Where it lives | Notes |
|---|---|---|
| `GITHUB_TOKEN` | Issued by GitHub Actions for each run | The release workflow uses it to push to GHCR (`packages: write`) and, on a manual run, to check that CI passed (`actions: read`). The uptime workflow uses it to open and close issues (`issues: write`). The workflows use no other repository secret. |
| `SENTRY_DSN_WEB` | GitHub repository variable (not a secret) | The web image's Sentry DSN (project `zyrcle-web`), passed as a build argument. Set on 2026-11-26. |
| Sentry account | Organization `aiteralabs` (Diego's), projects `zyrcle-api`, `zyrcle-web` and `zyrcle-mobile`, created 2026-11-25 | Its DSNs go in three places, all set on 2026-11-26: `SENTRY_DSN_API` in `deploy/.env`, `SENTRY_DSN_WEB` above, and `EXPO_PUBLIC_SENTRY_DSN` as an EAS variable with visibility sensitive, since builds on the Mac cannot read secret ones ([ADR 0033](adr/0033-error-reports-and-uptime.md)). |
| Off-site bucket and age key | none yet | A Cloudflare R2 bucket with a lifecycle rule and a lock, a token scoped to it, and an age key pair whose private half only Diego keeps, offline ([ADR 0034](adr/0034-encrypted-off-site-backups.md)). |
| Anthropic account | none yet | An API key with a monthly spending limit ([ADR 0038](adr/0038-reading-scale-tickets-with-ai.md)). |
| Pinata account | Pinata; the JWT is in `deploy/.env` | Placed by Diego on 2026-11-23 ([history.md](history.md)). |
| Expo account and EAS project | `@diegowritescode/zyrcle`, project ID in [app.json](../apps/mobile/app.json) | Builds run on EAS ([ADR 0015](adr/0015-android-builds.md)). |
| `GOOGLE_SERVICES_JSON` | EAS secret file variable (environments development, preview, production) and Diego's private folder | Firebase project `zyrcle-18c69`, app `xyz.deviego.zyrcle`. Kept out of git by [apps/mobile/.gitignore](../apps/mobile/.gitignore). |
| FCM v1 service-account key | EAS credentials and Diego's private folder | Lets EAS and Expo deliver Android push through Firebase ([ADR 0015](adr/0015-android-builds.md)). |
| Android signing keystore | Held by Expo | Signs the APKs and app bundles ([ADR 0015](adr/0015-android-builds.md)). A build on the Mac fetches it from Expo for its duration ([ADR 0043](adr/0043-android-builds-on-the-mac.md)). Certificate SHA-256 `0f3637b0ac3a7d122edc6c45d4527ce56fead9434835b555c745714f7ab4107d`, checked by `build-apk.sh`. |
| Resend account and verified domain | Resend | Not described further in the repository. |
| Apple Developer account | none recorded | iOS push and builds need one ([ADR 0008](adr/0008-push-notifications.md)). |

## 7. ZyrcleChain

### 7.1 What it is

ZyrcleChain v2 is Zyrcle's own Avalanche L1 on Fuji, running Subnet-EVM. Its native coin is ZYR,
and 1 ZYR stands for 1 Colombian peso (1e18 wei = 1 peso). The coin residents are paid in is also
the gas token, so residents never buy gas ([ADR 0002](adr/0002-own-avalanche-l1.md)). It has been
live since 2026-11-22. Its genesis, node configuration and setup scripts live in
[infra/l1](../infra/l1/README.md), so the chain can be recreated.

| Parameter | Value |
|---|---|
| EVM chain ID | 20261121 |
| Subnet ID | `YZ1nRuEqM6LGAJoQqEkyirLvQbfxps8LutUBKFPGaYRjYSjMN` |
| Blockchain ID | `hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8` |
| VM ID | `srEXiWaHuhNyGwPUi444Tu47ZEDwxTWrbQiuD7FmgSAQ6X7Dy` (standard Subnet-EVM) |
| Validator management | Proof of Authority (PoA): a validator manager contract predeployed in genesis, at `0x0Feedc0de0000000000000000000000000000000` |
| Conversion to L1 | transaction `2cUd7JCsXskJHzajqkj5iNaAWEqaK5KR3VxdctJYSTZfwgEwts` |
| Genesis supply | 100 ZYR to the L1 admin for gas (the "genesis float"). Nothing else. |
| Fees | `minBaseFee` 25 gwei, gas limit 8,000,000, target block rate 2 s. A plain transfer costs about 0.000525 ZYR. |
| Node software | AvalancheGo v1.15.3, Subnet-EVM plugin version 47 |

All IDs are also in [infra/l1/fuji.env](../infra/l1/fuji.env).

### 7.2 Precompiles

The genesis ([genesis.fuji.json](../infra/l1/genesis.fuji.json)) made the L1 admin key
(`0xfdDD…2f7d`) the admin of every allow-list precompile. Since 2026-11-23 the admin Safe
(`0x607c…E43b`) is, and the L1 admin key holds no role on any of them (runbook 9.14).

| Precompile | Address | What Zyrcle uses it for |
|---|---|---|
| ContractDeployerAllowList | `0x0200000000000000000000000000000000000000` | Only listed addresses deploy contracts. The guardian (oracle key) is listed so it can deploy smart accounts on their first recovery. The L1 admin key is no longer listed, so it cannot deploy. |
| NativeMinter | `0x0200000000000000000000000000000000000001` | The Treasury `0xd705…0Aeb` is the only enabled minter. The Safe, as admin, could also mint, with two signatures. |
| FeeManager | `0x0200000000000000000000000000000000000003` | Enabled; fees are set in genesis. |
| RewardManager | `0x0200000000000000000000000000000000000004` | Enabled. ADR 0002 says fees go to the treasury. The genesis sets no reward address, and no script in the repository sets one. |
| Warp | `0x0200000000000000000000000000000000000005` | Enabled from genesis for a future bridge. The L1's own validators sign P-Chain Warp messages (`requirePrimaryNetworkSigners: false`). |

Foundry scripts cannot call Subnet-EVM precompiles, which is why contracts are not deployed with
`forge script` ([chain/README.md](../chain/README.md)).

### 7.3 Validator

- One validator, `NodeID-LEXURXpvabdwVCyUZeTUKLFPf2won5DXp`, weight 100, on the VPS
  ([section 4.4](#44-the-l1-node-project-zyrcle-l1)).
- The validator manager `0x0Feedc0de0000000000000000000000000000000` is a transparent proxy. Both
  it and its proxy admin `0xa0Affe1234567890aBcDEF1234567890ABCdEf34` (which can upgrade it) are
  owned by the Safe since 2026-11-23.
- It was funded with a 4.7 AVAX fee balance at the conversion
  ([infra/l1/README.md](../infra/l1/README.md)).
- **Continuous validator fee.** The P-Chain deducts a fee from that balance continuously. At the
  funding of 2026-11-22 it lasts until about **2027-03-09**. It is topped up by hand, and Diego must
  be reminded before then ([ADR 0021](adr/0021-l1-operations.md)). If it runs out, the chain halts.
  The 2025 chain died this way ([ADR 0002](adr/0002-own-avalanche-l1.md)). See
  [runbook 9.8](#98-top-up-the-validator).

### 7.4 Contracts on Fuji

| Contract or role | Address | Source |
|---|---|---|
| Treasury | `0xd7052201140224018b123ecFF7b83B4251790Aeb` | [Treasury.sol](../chain/src/Treasury.sol) with the host share and redemptions, deployed 2026-11-23 with `zyrcle-api chain deploy` ([ADR 0029](adr/0029-closed-loop-payments.md)), shares 65/15/10/10; admin (`DEFAULT_ADMIN_ROLE`: shares, pause, roles) is the Safe |
| Second Treasury (no longer used) | `0xBc5035341C075CBd75508ff1a3a5EC0241e58201` | deployed 2026-11-22 with the host share ([ADR 0013](adr/0013-sale-and-settlement.md)); never minted; off the NativeMinter allow list since 2026-11-23 |
| First Treasury (no longer used) | `0xB843946A42F2791B8b932F8c0205C9D277E351B1` | deployed 2026-11-21, before the host share; off the NativeMinter allow list since 2026-11-23 |
| Treasury operator (`OPERATOR_ROLE`) | `0x528815e03Aa80b045B32840f3e26B394D0838d0d` | `fuji.env` `TREASURY_OPERATOR` |
| Treasury oracle (`ORACLE_ROLE`) | `0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50` | `fuji.env` `TREASURY_ORACLE` |
| Seed capital transaction | `0x0e58542108f3e94c92ffd93b2d0576128e75199ed4449c676ce51be4cb82e05a` | 1,000,000 COP, simulated, ref `keccak256("testnet-simulated-seed")`, in the current Treasury (the second one's was `0x802b19d9…009d`, the first one's `0x4e865bc7…424c`) |
| AccountFactory | `0x0bE806Ca77340aA50AF6586CDC2FE2561668DaEA` | [AccountFactory.sol](../chain/src/AccountFactory.sol), deployed 2026-11-22 with `zyrcle-api chain accounts-deploy`; admin (`DEFAULT_ADMIN_ROLE`: names the guardian) is the Safe |
| ZyrcleAccount implementation | `0x008094fd22255b4d91846eb93042d0f05212b79f` | deployed by the factory's constructor |
| Guardian | `0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50` | the oracle key, until runbook 9.13 |
| Admin Safe (2 of 3) | `0x607c011C6921eA75C1e38223a5E5514eDbA7E43b` | Safe v1.4.1 ([ADR 0040](adr/0040-keys-guardian-and-multisig.md)), vendored in [chain/lib/safe-smart-account](../chain/lib/safe-smart-account/README.md). Holds every admin power since 2026-11-23: the four precompiles, the validator manager and its proxy admin, the Treasury and AccountFactory admin roles. Owners in section 6.1 |
| Safe helper contracts | singleton `0x0a9c029567e8E55dD59D6d4934CA93c1814c0bfc`, proxy factory `0x6d5DE6C6a0928e622bb652e009a9FF1fb8685075`, fallback handler `0xabd43Ca3a4AF298E327C1Bf8021fda16f0d7c73e`, MultiSendCallOnly `0xe2B3F3B36B858dF247b89F762E3efba6653a603C` | deployed by `zyrcle-api safe deploy` with the Safe; `SAFE_*` in `fuji.env` |
| Validator manager, its proxy admin | `0x0Feedc0de0000000000000000000000000000000`, `0xa0Affe1234567890aBcDEF1234567890ABCdEf34` | predeployed in genesis; owner of both is the Safe |
| Executed Safe proposals | [infra/l1/safe/](../infra/l1/safe/README.md) | `1-proof.json` and `2-revoke.json`, the signed files of the handover, kept as the audit trail |

Advance limits are 5,000 COP per deposit and 20,000 COP per resident per UTC day
([ADR 0023](adr/0023-testnet-economics.md)).

> **The Treasury was redeployed on 2026-11-22** for the host share (ADR 0013, amendments). The new
> one does not know the advances the first one paid; the settlement worker subtracts those from what
> it sends, using the advances recorded in the `payout` table, so nobody is paid an advance twice.
>
> **It was redeployed again on 2026-11-23** for redemptions (ADR 0029). The second Treasury had
> minted nothing, so no advance carries over. Both earlier Treasuries were then taken off the
> NativeMinter allow list (`chain minter-revoke`, runbook 9.6): only the current one can mint.
> Both redeploys happened before the handover to the Safe, with the L1 admin key.

### 7.5 How contracts are deployed

Deployment goes through the backend's command line, so keys stay in files on the server
([cli.py](../apps/api/src/zyrcle_api/cli.py)):

| Command | What it does |
|---|---|
| `zyrcle-api chain deploy --admin-key-file F --operator 0x.. --oracle 0x.. [--max-advance-cop 5000] [--daily-cap-cop 20000]` | Deploys the Treasury with the key's address as its admin and shares 65/15/10/10, grants the two roles, and puts the Treasury on the NativeMinter allow list. |
| `zyrcle-api chain seed --operator-key-file F --amount-cop N --ref TEXT` | Records seed capital. The reference is stored as `keccak256(TEXT)`. |
| `zyrcle-api chain state` | Prints backing, minted, available, seed capital and operations revenue, in COP. |
| `zyrcle-api chain accounts-deploy --admin-key-file F --guardian 0x..` | Deploys the AccountFactory and puts the guardian on the ContractDeployerAllowList. |
| `zyrcle-api chain accounts-guardian --admin-key-file F --guardian 0x..` | Adds the new guardian to the allow list and makes it the factory's guardian. Needs `ZYRCLE_ACCOUNT_FACTORY_ADDRESS`. |
| `zyrcle-api chain minter-revoke --admin-key-file F --address 0x..` | Takes a retired Treasury off the NativeMinter allow list, so it can no longer mint. Refuses the Treasury in `ZYRCLE_TREASURY_ADDRESS`; does nothing if the address is already off. |
| `zyrcle-api chain fund --from-key-file F --to 0x.. --amount-zyr N` | Sends native ZYR (gas) from one key to an address and prints both balances. |
| `zyrcle-api chain balance --address 0x..` | Prints an address's native ZYR. |
| `zyrcle-api keys new --out FILE` | Writes a new private key to a `0600` file and prints only its address. Refuses to overwrite. |
| `zyrcle-api safe deploy --admin-key-file F --owners A,B,C --threshold 2` | Deploys the Safe's singleton, proxy factory, fallback handler and MultiSendCallOnly, then a Safe; prints the `SAFE*` lines for `fuji.env`. |
| `zyrcle-api safe status --safe S --admin A` | For each admin power found on the chain, whether address `A` and the Safe hold it. |
| `zyrcle-api safe grant`, `own`, `renounce` (`--admin-key-file F --safe S`) | Handover steps 1, 3 and 5, sent from the key that held the powers (runbook 9.14). |
| `zyrcle-api safe propose --safe S --what proof\|revoke\|guardian\|call … --out FILE` | Writes a proposal: the handover's proof and revoke steps, a new guardian (`--guardian G --multisend M`), or any one call (`--to T --data 0x… --description TEXT`). It carries the Safe's current nonce. |
| `zyrcle-api safe sign --proposal FILE --key-file F\|-` | Adds an owner's signature to the file; `-` asks for the key at a prompt without showing it. Checks the signer is an owner. |
| `zyrcle-api safe exec --proposal FILE --key-file F` | Sends a proposal with enough signatures. `F` only pays the gas. Refuses a proposal whose hash or nonce no longer matches the Safe. |

The `chain` commands that take `--admin-key-file` were written for a key that is the precompiles'
admin. Since the handover no key file is, and the L1 admin key is on no allow list: `chain deploy`,
`chain accounts-deploy`, `chain accounts-guardian` and `chain minter-revoke` fail with it. What they
did as admin (enabling a minter or a deployer, naming the guardian, revoking a minter) is now a Safe
proposal (runbooks 9.6, 9.13, 9.14).

On the VPS these run through
[infra/l1/scripts/zyrcle-api-docker.sh](../infra/l1/scripts/zyrcle-api-docker.sh), because the host
has no `python3-venv` ([ADR 0020](adr/0020-single-vps-docker-compose.md)). The wrapper:

- runs `python:3.13-slim` with host networking, as the calling user, with standard input attached;
- sources `infra/l1/fuji.env` and passes only `ZYRCLE_CHAIN_RPC_URL`
  (`http://127.0.0.1:9650/ext/bc/<BLOCKCHAIN_ID>/rpc`), `ZYRCLE_TREASURY_ADDRESS` (`TREASURY`) and
  `ZYRCLE_ACCOUNT_FACTORY_ADDRESS` (`ACCOUNT_FACTORY`);
- mounts the repository and `~/.avalanche-cli/key` at `/keys`, read-only except for `keys new`,
  which writes there;
- creates `apps/api/.venv-docker` with an editable install the first time only, then runs
  `zyrcle-api` from it. It runs the checkout's code, not the deployed image's.

```bash
infra/l1/scripts/zyrcle-api-docker.sh chain state
```

`safe propose --what guardian` and `--what call` arrived in commit `fd05fa7`, after the deployed
images; the wrapper has them once the checkout includes that commit.

The backend deploys exactly what `forge build` produces: CI fails if the exported ABI and bytecode in
`apps/api/src/zyrcle_api/contracts` differ ([ADR 0007](adr/0007-on-chain-treasury.md)).

### 7.6 Recreating the chain

[infra/l1/README.md](../infra/l1/README.md), "Runbook: recreate the chain", has eleven steps:
install the pinned tools, create the P-Chain and admin keys, fund the P-Chain key, start the node,
generate the genesis, create the subnet, chain and L1 with `platform-cli`, track the L1, initialize
the validator manager with the Avalanche CLI, publish the RPC, run the smoke test, then deploy the
contracts and move the admin powers to a Safe. Tool choice:
`platform-cli` 2.4.0 for P-Chain work, Avalanche CLI 1.9.7 only for genesis generation and validator
manager initialization ([ADR 0021](adr/0021-l1-operations.md)).

A new chain has new IDs. Every place that names them changes: `fuji.env`, `node.json`
(`track-subnets`), `chains/<BlockchainID>/`, `deploy/.env` and `deploy/.env.example`,
`apps/web/Dockerfile`, `apps/web/src/lib/config.ts`, `apps/mobile/src/lib/config.ts`,
`.github/workflows/uptime.yml` (the RPC URL) and `infra/l1/README.md`. All contracts must be
deployed again, with the new admin key while it still holds the genesis powers, and balances on the
old chain do not carry over.

## 8. CI/CD

### 8.1 CI ([.github/workflows/ci.yml](../.github/workflows/ci.yml))

CI runs on every push to `main` and on every pull request. A newer run on the same ref cancels the
older one. The nine jobs run in parallel:

| Job | What it checks |
|---|---|
| `packages` | `ruff` lint and format, `pytest` for `packages/protocol` and `device/simulator`. |
| `api` | `ruff`; `alembic upgrade head` on an empty database, then `alembic check` (migrations match the models); `pytest` against Postgres, Mosquitto and anvil, failing under 75 % line coverage (the floor of [ADR 0031](adr/0031-testing-and-the-pre-production-check.md)). |
| `e2e` | On `ubuntu-24.04`, 30-minute limit: starts the whole stack from the checkout (`e2e/stack/up.sh`, `apps.sh`), typechecks the tests and runs every Playwright journey in Chromium ([e2e/README.md](../e2e/README.md)). On failure it keeps the stack logs and the Playwright report as an artifact for 14 days. |
| `chain` | `forge soldeer install`, `forge fmt --check`, `forge build --sizes`, `forge test`; then `export-artifacts.py` and `git diff --exit-code` on the backend's contract artifacts (the Safe's included) and test fixtures. |
| `images` | Builds both Docker images (not pushed) and validates `deploy/compose.yml` with placeholder values, the images given as digests. |
| `client` | Typecheck and tests of `packages/client`, failing under 50 % line coverage. |
| `mobile` | Typecheck, `expo lint`, `npm test`, and `expo export` for iOS and Android. |
| `web` | Typecheck, `eslint`, `vitest` with coverage, production build. |
| `infra` | `shellcheck -x` on `infra/l1/scripts/*.sh`, `deploy/*.sh` and `e2e/stack/*.sh`; `deploy/offsite-selftest.sh` (the off-site copy encrypts, uploads and restores, against an S3 stand-in, [ADR 0034](adr/0034-encrypted-off-site-backups.md)); the L1 scripts' Python unit tests; a build of the validator image. |

### 8.2 Release ([.github/workflows/release.yml](../.github/workflows/release.yml))

- Trigger: the CI workflow completes on `main` with conclusion `success`. A manual
  `workflow_dispatch` also runs it, but its first step stops unless a CI run for that commit
  succeeded (`gh run list --workflow CI --commit <sha> --status success`,
  [ADR 0032](adr/0032-deploys-pinned-recorded-and-backed-up.md)).
- It checks out the exact commit CI tested and builds with Buildx, using the GitHub Actions cache.
- It pushes `ghcr.io/diegowritescode/zyrcle-api:<sha>` (API and simulator) and
  `ghcr.io/diegowritescode/zyrcle-web:<sha>`, labelled with the source repository. The web image
  gets `VITE_SENTRY_DSN` from the repository variable `SENTRY_DSN_WEB` (unset: no reports) and
  `VITE_RELEASE` set to the SHA.
- Its step summary prints both images by digest and the deploy command `deploy/deploy.sh <sha>
  <sha>`, which pins those digests and records them in `deploy/history.log`.
- Deploying is a separate, manual step. Nothing deploys automatically.

```mermaid
flowchart TB
  trigger["Push to main or pull request"] --> packages & apij & e2ej & chainj & imagesj & clientj & mobilej & webj & infraj
  subgraph ci["CI workflow ci.yml: nine jobs in parallel"]
    packages["packages<br/>ruff, pytest: protocol, simulator"]
    apij["api<br/>ruff, alembic upgrade and check, pytest<br/>with Postgres, Mosquitto, anvil, coverage 75"]
    e2ej["e2e, ubuntu-24.04<br/>whole stack, Playwright journeys"]
    chainj["chain<br/>forge fmt, build, test<br/>ABI drift check"]
    imagesj["images<br/>docker build api and web<br/>compose config check"]
    clientj["client<br/>typecheck, tests"]
    mobilej["mobile<br/>typecheck, lint, tests, expo export"]
    webj["web<br/>typecheck, eslint, tests, build"]
    infraj["infra<br/>shellcheck, off-site self-test,<br/>unittest, validator image build"]
  end
  packages & apij & e2ej & chainj & imagesj & clientj & mobilej & webj & infraj --> gate{"Whole workflow succeeded<br/>on main?"}
  gate -->|"no"| stop["No images"]
  gate -->|"yes"| checkout
  dispatch["Manual workflow_dispatch"] --> passed{"CI passed<br/>for this SHA?"}
  passed -->|"no"| stop
  passed -->|"yes"| checkout
  subgraph rel["Release images release.yml"]
    checkout["Check out the tested SHA"] --> pushapi["Build and push zyrcle-api:SHA"] --> pushweb["Build and push zyrcle-web:SHA"] --> summary["Step summary:<br/>both digests,<br/>deploy/deploy.sh SHA SHA"]
  end
  pushapi --> ghcr[("GHCR")]
  pushweb --> ghcr
  subgraph vps["On the VPS, manual, needs Diego's approval"]
    deploy["ssh aitera-vps<br/>cd ~/apps/zyrcle, git fetch, git checkout SHA<br/>deploy/deploy.sh api-sha web-sha"]
  end
  summary -.->|"copy the full SHA"| deploy
  ghcr -->|"docker pull, pinned by digest"| deploy
  subgraph mob["Mobile, manual, not in CI"]
    localcmd["apps/mobile/scripts/build-apk.sh<br/>preview or development"] --> easlocal["eas build --local<br/>on Diego's Mac"] --> artifact["APK: development, preview<br/>app bundle: production"]
    eascmd["npx eas-cli build --profile<br/>development, preview or production"] --> easbuild["EAS cloud build<br/>@diegowritescode/zyrcle"] --> artifact
  end
```

### 8.3 Deploy procedure

`deploy/deploy.sh <api-sha> <web-sha>` is idempotent: running it twice with the same SHAs changes
nothing. Step by step ([deploy.sh](../deploy/deploy.sh)):

1. **Check the tags and the checkout.** Both tags must be full 40-character SHAs. The checkout must
   be the commit whose API is deployed, because `compose.yml`, the broker files and the script come
   from it; `DEPLOY_ANY_CHECKOUT=1` allows another one, to roll back only the web app.
2. **Pull and pin the two images.** Each pull is cut after 5 minutes and tried up to three times (a
   pull hung on 2026-11-23). The images' digests are read from the pulled images. `SKIP_PULL=1`
   uses images already on the machine.
3. **Secrets, first run only.** If `deploy/.env` is missing, create it from `.env.example` with
   `umask 077` and fresh values from Python's `secrets.token_urlsafe` (see
   [section 5.2](#52-deployenv)). Set the key paths to `$HOME/.avalanche-cli/key/zyrcle-oracle.pk`
   and `zyrcle-operator.pk`, `GUARDIAN_KEY_PATH` to the oracle key's file too, and the UID and GID
   to the current user's.
4. **Update `.env`.** Rename the legacy variable names; add `GUARDIAN_KEY_PATH` with the value of
   `ORACLE_KEY_PATH` if it is missing; write the two tags and the two images pinned by digest
   (`ZYRCLE_API_IMAGE`, `ZYRCLE_WEB_IMAGE`, added if missing), then load the file. Compose runs the
   images by digest.
5. **Broker accounts.** Hash the five broker passwords with `mosquitto_passwd` in a throwaway
   container of the pinned Mosquitto image. Install the result as `mosquitto/passwd` and copy the ACL
   to `mosquitto/acl.runtime`, both `0600`.
6. **Database, backup, migrations.** Pull any other image compose names that is missing, start
   `postgres` and `mosquitto` and wait for them, back up the database with `backup.sh`, then run
   `docker compose --profile ops run --rm migrate` (`alembic upgrade head`). The running API is not
   stopped first.
7. **Simulated containers.** Start `sim` and wait up to 30 s for `/keys/ctr-0004.pub.pem`. Then run
   `zyrcle-api demo seed` in a one-off `api` container with the `zyrcle_sim-keys` volume mounted
   read-only. The seed registers the demo host, sites, containers, bags and test prices, and is safe
   to repeat.
8. **Services.** `docker compose up -d --remove-orphans api web sim mosquitto postgres`, then print
   each service's status. `--remove-orphans` removes services no longer in the file; the L1 node is
   another project and is not touched.
9. **Record it.** Append a line to `deploy/history.log` (not in git): the time, both images by
   digest, the migration revision and the user. That file is what a rollback reads.

Things `deploy.sh` does not do:

- It does not add new variables to an existing `.env`, except the two image variables and
  `GUARDIAN_KEY_PATH`.
- It does not restart Mosquitto when the broker files change.
- It does not downgrade the database for a rollback across migrations (runbook 9.2).

### 8.4 Rollback

Check out the previous commit and run `deploy.sh` with the previous SHAs; `deploy/history.log`
names them. This works as long as no migration was added in between. If one was, the older image
cannot migrate the newer database, and the database must be downgraded first, or restored from the
dump `deploy.sh` took before migrating. [Runbook 9.2](#92-roll-back) has the steps. Contract
deployments and on-chain state cannot be rolled back.

### 8.5 Mobile build path

Builds run on Diego's Mac with EAS's own runner (`eas build --local`), through
[apps/mobile/scripts/build-apk.sh](../apps/mobile/scripts/build-apk.sh)
([ADR 0043](adr/0043-android-builds-on-the-mac.md)). It is the cloud's build on this machine: the
same profiles, the EAS project `@diegowritescode/zyrcle` and its variables, and the signing key Expo
keeps. Expo's cloud remains for when the Mac is not available
([ADR 0015](adr/0015-android-builds.md)). CI only typechecks, lints and bundles the app; it never
calls EAS.

| Profile ([eas.json](../apps/mobile/eas.json)) | Output | Use |
|---|---|---|
| `development` | Development client, internal distribution, APK | Replaces Expo Go for testing push. |
| `preview` | Internal distribution, APK, pointed at production | Installable test build outside the Play Store. |
| `production` | Store build, version number auto-incremented | Kept for the Play Store. It needs an `.aab`, a privacy policy and the data safety form (roadmap M7). `build-apk.sh` refuses it until then. |

```bash
apps/mobile/scripts/build-apk.sh            # preview; or: build-apk.sh development
```

- The APK lands in `apps/mobile/dist-apk/zyrcle-<profile>-<commit>.apk` (ignored by git). The script
  refuses to start with uncommitted changes in `apps/mobile` or `packages/`, and refuses the result
  unless it is signed with Expo's key (SHA-256 in section 6.3), has Firebase's app ID and carries
  ARM code only.
- Toolchain, all from Homebrew: `openjdk@21` (Gradle for Android does not run on newer Java) and
  `android-commandlinetools` with `platform-tools`, `platforms;android-36`, `build-tools;36.0.0` and
  the NDK, under `/opt/homebrew/share/android-commandlinetools`. Diego's Expo session must be open
  (`npx eas-cli whoami`).
- A build takes about 8 minutes and compiles all native code each time: every build starts from a
  clean copy of the repository.
- Variables come from the EAS environment named by the profile, but only those with visibility
  plain text or sensitive. `GOOGLE_SERVICES_JSON` is secret, so the script points it at
  `apps/mobile/google-services.json`.
- App version numbers come from EAS (`appVersionSource: remote`). Every `preview` APK so far has
  version code 1. The app ID is `xyz.deviego.zyrcle`.
- Native code is built for `armeabi-v7a` and `arm64-v8a` only. x86 emulators cannot install the
  APKs ([app.config.ts](../apps/mobile/app.config.ts)).
- A cloud build (`npx eas-cli@latest build --profile preview --platform android`) uses the free
  plan's monthly quota and needs Diego's approval
  ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)).
- `eas submit` has an empty `production` entry. No store submission is recorded.
- No iOS build is recorded. iOS needs an Apple Developer account.
- First-time setup (Firebase project, `GOOGLE_SERVICES_JSON`, FCM key) is in
  [apps/mobile/README.md](../apps/mobile/README.md), "Notifications".

## 9. Runbooks

Before any of these:

- **Get Diego's approval** for deploying, deleting, contract transactions on Fuji, installing
  software on the VPS and EAS builds on Expo's cloud ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)).
- Work on the VPS as `diego`, from `~/apps/zyrcle`.
- `docker compose -f deploy/compose.yml …` reads `deploy/.env` automatically.
- Never print `deploy/.env` or a key file.
- Steps marked **Gap** have no script in the repository yet.

### 9.1 Deploy a new version

1. Check that CI and "Release images" passed for the commit. The images must exist in GHCR; the
   release's summary lists them by digest.
2. Deploy:
   ```bash
   ssh aitera-vps
   cd ~/apps/zyrcle && git fetch && git checkout <sha>
   deploy/deploy.sh <sha> <sha>
   git checkout main                       # afterwards, so the next git pull works
   ```
   `deploy.sh` stops unless the checkout is the API's commit, because it uses the checkout's
   `compose.yml` and broker files. `git pull` on `main` and `deploy/deploy.sh $(git rev-parse HEAD)
   $(git rev-parse HEAD)` does the same for the newest commit.
3. `deploy.sh` cuts a pull after 5 minutes and tries three times (a pull hung at "Pulling fs layer"
   on 2026-11-23). If all three fail, pull each image by hand with `docker pull
   ghcr.io/diegowritescode/zyrcle-api:<sha>` (and `zyrcle-web`), then run `SKIP_PULL=1
   deploy/deploy.sh <sha> <sha>`. Run it with `nohup` and a log file so a dropped SSH session does
   not stop it halfway.
4. If compose stops with "set … in deploy/.env", the new `compose.yml` needs a variable that the
   existing `.env` lacks. Add it from `deploy/.env.example` and run `deploy.sh` again.
   `OPERATOR_KEY_PATH` (ADR 0013) is one example.
5. Check ([deploy/README.md](../deploy/README.md)):
   ```bash
   docker compose -f deploy/compose.yml ps
   curl -s https://zyrcle-backend.deviego.xyz/health          # {"ok":true,"mqtt":true}
   curl -s https://zyrcle-backend.deviego.xyz/v1/stats
   curl -s https://zyrcle-backend.deviego.xyz/v1/demo/containers
   curl -sI https://zyrcle.deviego.xyz | grep -i content-security-policy
   ```

### 9.2 Roll back

1. **Find the previous deploy.** `deploy/history.log` has one line per deploy: time, both images by
   digest, migration revision, user. The commit SHA is the image tag, also on the "Release images"
   run of that commit.
   ```bash
   tail -5 ~/apps/zyrcle/deploy/history.log
   ```
2. **No migration in between.** Check out the older commit and deploy it:
   ```bash
   git fetch && git checkout <previous-api-sha>
   deploy/deploy.sh <previous-api-sha> <previous-web-sha>
   git checkout main                 # afterwards, so the next git pull works
   ```
   To roll back only the web app, stay on the current checkout and run
   `DEPLOY_ANY_CHECKOUT=1 deploy/deploy.sh <current-api-sha> <previous-web-sha>`.
3. **A migration in between.** The older image's `alembic upgrade head` fails, because the database
   is at a revision that image does not know. `deploy.sh` stops there and the newer API keeps
   running. **Gap:** this path is not scripted. Downgrade with the newer image still in `.env`, then
   deploy the older SHAs:
   ```bash
   docker compose -f deploy/compose.yml --profile ops run --rm migrate alembic downgrade <revision>
   deploy/deploy.sh <previous-api-sha> <previous-web-sha>
   ```
   Revisions are `0001` to `0016` ([apps/api/migrations/versions](../apps/api/migrations/versions));
   `history.log` names the one each deploy left. A downgrade drops the tables and columns the newer
   migrations added, with their data. The alternative is restoring the dump `deploy.sh` took just
   before the newer migration (the newest file in `~/backups/zyrcle` from that deploy's time,
   runbook 9.10), which loses what was written since.
4. Contract deployments, on-chain payments and installed mobile builds cannot be rolled back.

### 9.3 Run a migration

- **Normal path.** Every `deploy.sh` run applies `alembic upgrade head` before starting the new API.
- **On its own,** with the image named by `ZYRCLE_API_IMAGE` in `deploy/.env`:
  ```bash
  docker compose -f deploy/compose.yml --profile ops run --rm migrate
  ```
- **Current revision** (overrides the service's command; not scripted):
  ```bash
  docker compose -f deploy/compose.yml --profile ops run --rm migrate alembic current
  ```
- **Writing a migration.** Migrations live in `apps/api/migrations/versions/`, numbered, each with a
  `downgrade`. CI applies them to an empty database and runs `alembic check`, so a model change
  without a migration fails CI.
- `deploy.sh` backs up the database before migrating (section 8.3).

### 9.4 Rotate the Treasury operator or oracle key

The Treasury's roles belong to its admin, the Safe, so moving one takes Safe proposals signed by
two owners (runbook 9.14). **Gap:** no command builds the calldata of a role change or a pause;
build it with Foundry's `cast` (inline below; where `cast` is not installed, run it on another
machine and paste the `0x…` it prints) and pass it to `safe propose --what call`. Set
`W=infra/l1/scripts/zyrcle-api-docker.sh` and `source infra/l1/fuji.env` first, for `SAFE` and
`TREASURY`.

1. **In an emergency, pause first.** `pause()` stops advances and settlements
   ([ADR 0007](adr/0007-on-chain-treasury.md)); it needs two signatures like any other admin call:
   ```bash
   $W safe propose --safe $SAFE --what call --to $TREASURY --function 'pause()' \
     --description "Pausar la tesorería" --out ../../infra/l1/safe/<n>-pause.json
   ```
   `unpause()` undoes it the same way.
2. **Create the new key on the VPS.** It prints only the address:
   ```bash
   $W keys new --out /keys/zyrcle-operator-2.pk
   ```
   The file lands in `~/.avalanche-cli/key/` as `0600`. Add it to the offline inventory
   ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)).
3. **Give it gas.** Send it a few ZYR from the L1 admin's float with `chain fund` (runbook 9.12).
4. **Move the role.** Two proposals, one after the other (each carries the Safe's nonce, so make the
   second after the first has run). The role is `OPERATOR_ROLE` or `ORACLE_ROLE`:
   ```bash
   $W safe propose --safe $SAFE --what call --to $TREASURY \
     --function 'grantRole(bytes32,address)' --args OPERATOR_ROLE <new> \
     --description "Nuevo operador de la tesorería" --out ../../infra/l1/safe/<n>-grant.json
   # sign and exec (runbook 9.14); then the same with 'revokeRole(bytes32,address)' and the old one
   ```
5. **Oracle only: the guardian.** While `GUARDIAN_KEY_PATH` points at the oracle key, the oracle is
   also the AccountFactory guardian. Give the guardian its own key first (runbook 9.13), so the
   oracle can move alone. The old oracle stays on the ContractDeployerAllowList until a proposal
   calls `setNone(<old address>)` on `0x0200000000000000000000000000000000000000`.
6. **Point the API at the new file.** Change `OPERATOR_KEY_PATH` or `ORACLE_KEY_PATH` in
   `deploy/.env`, then redeploy the current version so compose recreates `api` with the new mount.
   `deploy.sh` wants the checkout at the deployed API commit (section 8.3):
   ```bash
   grep -E '^ZYRCLE_(API|WEB)_TAG=' deploy/.env      # the current tags; prints no secret
   git checkout <current-api-sha>
   deploy/deploy.sh <current-api-sha> <current-web-sha>
   git checkout main
   ```
7. **Record it.** Update `TREASURY_OPERATOR`, `TREASURY_ORACLE` or `ACCOUNT_GUARDIAN` in
   `infra/l1/fuji.env`, and the table in `chain/README.md`.

### 9.5 Rotate the shared operator token or another `deploy/.env` secret

`deploy.sh` generates secrets only when `deploy/.env` does not exist. To rotate one, replace its
line by hand (in an editor, without printing the file), then redeploy the current version.

1. Generate a value the same way `deploy.sh` does:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Replace the line in `deploy/.env`.
3. Redeploy the current tags (see 9.4, step 6). Compose recreates every service whose environment
   changed.

What each rotation does:

| Secret | Effect and extra steps |
|---|---|
| `OPERATOR_TOKEN` | Scripts with the old token stop working. Operators' own accounts are unaffected. ADR 0014 asks for this rotation once operators have their own accounts. |
| `JWT_SECRET` (at least 32 characters) | Every resident and operator session ends. Emailed codes still pending stop matching. |
| `MQTT_*_PASSWORD` | `deploy.sh` rehashes `mosquitto/passwd` but does not restart Mosquitto, which reads that file at start. Restart it: `docker compose -f deploy/compose.yml restart mosquitto`. The API and the simulator reconnect by themselves. |
| `POSTGRES_PASSWORD` | **Gap.** The Postgres image applies this variable only when it initializes an empty data directory. Changing the line alone breaks the API's connection. Changing the database user's password is not scripted. |
| `RESEND_API_KEY`, `EXPO_ACCESS_TOKEN`, `PINATA_JWT`, `ANTHROPIC_API_KEY`, `SENTRY_DSN_API`, `OFFSITE_S3_*` | Diego places these himself over SSH ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)). Revoke the old key in the provider's dashboard. `offsite.sh` reads `deploy/.env` on each run, so the `OFFSITE_*` lines need no redeploy. |

### 9.6 Redeploy the Treasury

It was done twice, for the host share (ADR 0013) and for redemptions (ADR 0029)
([section 7.4](#74-contracts-on-fuji)), both times before the handover, with the L1 admin key. It is
a contract transaction on Fuji, so it needs Diego's approval.

**Gap: since the handover, step 2 is not scripted and has not been run.** `chain deploy` deploys
from the given key, makes that key the new Treasury's admin, grants the two roles and then puts the
Treasury on the NativeMinter allow list. Today the L1 admin key is on no allow list, so it can
neither deploy nor enable a minter, and only the Safe can enable one. Read from the code, untested,
a redeploy needs: a Safe proposal putting a deploying key on the ContractDeployerAllowList
(`setEnabled(address)` on `0x0200…0000`); the deployment and the role grants from that key (`chain
deploy` stops at the NativeMinter step with an error, before printing the address); a Safe proposal
`setEnabled(<new Treasury>)` on the NativeMinter `0x0200…0001`; with `TREASURY` updated in
`fuji.env`, `safe grant` and `safe renounce` from the deploying key, so the Safe becomes the new
Treasury's admin and the key stops being it; and a Safe proposal taking the deploying key off the
deployer list (`setNone`). A command for this is missing.

1. **Update the code.** `git pull` on the VPS. The wrapper's editable install runs the checked-out
   code and contract artifacts. It creates `apps/api/.venv-docker` only when it is missing.
2. **Deploy.** The defaults give shares 65/15/10/10, 5,000 COP per deposit and 20,000 COP per
   resident per day. Before the handover this was one command:
   ```bash
   infra/l1/scripts/zyrcle-api-docker.sh chain deploy \
     --admin-key-file /keys/zyrcle-l1-admin.pk \
     --operator 0x528815e03Aa80b045B32840f3e26B394D0838d0d \
     --oracle 0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50
   ```
   It printed the new address and put the new Treasury on the NativeMinter allow list. Now see the
   gap above.
3. **Record the address** as `TREASURY` in `infra/l1/fuji.env`. The wrapper reads it from there.
4. **Record the simulated seed again** ([ADR 0023](adr/0023-testnet-economics.md)):
   ```bash
   infra/l1/scripts/zyrcle-api-docker.sh chain seed \
     --operator-key-file /keys/zyrcle-operator.pk \
     --amount-cop 1000000 --ref testnet-simulated-seed
   infra/l1/scripts/zyrcle-api-docker.sh chain state
   ```
5. **Point everything at it.** `TREASURY` in `deploy/.env` and `deploy/.env.example`, the
   `VITE_TREASURY_ADDRESS` default in `apps/web/Dockerfile` and `apps/web/src/lib/config.ts`, and
   `chain/README.md`. Commit, wait for the release, then run `deploy.sh`.
6. **Retire the old contract.** It stays on the NativeMinter allow list, and the oracle key keeps its
   role there, so it could still mint up to its unused backing. Take it off the allow list once the
   new one is deployed and the API points at it. `chain minter-revoke` did this with the admin key
   before the handover; now it is a Safe proposal (runbook 9.14; `$W` and `$SAFE` as in 9.4):
   ```bash
   $W safe propose --safe $SAFE --what call --to 0x0200000000000000000000000000000000000001 \
     --function 'setNone(address)' --args <old Treasury> \
     --description "Retirar la tesorería anterior" --out ../../infra/l1/safe/<n>-minter.json
   ```
7. **Mind old advances.** The new contract's `advanceOf` is empty. When it settles a deposit whose
   advance the old contract paid, it does not subtract that advance (`_settleDeposit` in
   [Treasury.sol](../chain/src/Treasury.sol)). **Gap:** the repository does not say how to treat
   those deposits.

### 9.7 Add an operator

Operators are people who use the console. They sign in with a six-digit code sent by email
([ADR 0014](adr/0014-operator-accounts.md)).

1. **Email must work.** Without `RESEND_API_KEY`, the API runs no email worker, and sign-in codes are
   never sent.
2. **The first admin** is added with the shared token, through `POST /v1/operator/operators`
   ([operator_auth.py](../apps/api/src/zyrcle_api/operator_auth.py)). **Gap:** not scripted. Run it
   on the VPS in a subshell, so the secrets do not stay in your shell:
   ```bash
   ( set -a; . deploy/.env; set +a
     curl -s -X POST "https://${API_HOST}/v1/operator/operators" \
       -H "Authorization: Bearer ${OPERATOR_TOKEN}" -H "Content-Type: application/json" \
       -d '{"email": "name@example.org", "name": "Full Name", "role": "admin"}' )
   ```
3. **Everyone else** is added by an admin in the console at `https://zyrcle.deviego.xyz/console`.
   Roles are `admin` and `operator`. Only admins add, deactivate or promote operators. An admin
   cannot demote or deactivate themselves. Deactivating someone ends their session at once.
4. An admin who loses their mailbox is recovered with the shared token (ADR 0014).

### 9.8 Top up the validator

**Deadline:** about 2027-03-09, from the funding of 2026-11-22 ([ADR 0021](adr/0021-l1-operations.md)).
If the balance runs out, ZyrcleChain halts.

What the repository gives:

1. **The tool.** `platform-cli` 2.4.0 handles the validator balance
   ([infra/l1/README.md](../infra/l1/README.md), ADR 0021). It reads the P-Chain key from the
   environment, loaded from the file so it never appears in arguments:
   ```bash
   export AVALANCHE_PRIVATE_KEY=0x$(cat ~/.avalanche-cli/key/zyrcle-pchain.pk)
   ```
2. **Funds.** The P-Chain key (`P-fuji1n3qzgzxfxjk05qss6hjvgmhd94wa3tvsw0ygch`) pays. Test AVAX can be
   sent to it on the P-Chain directly. AVAX on its C-Chain address can be moved with
   `avalanche key transfer --c-chain-sender --p-chain-receiver`. If that transfer stops halfway
   (Avalanche CLI 1.9.7 fails after the export), finish it:
   ```bash
   cd infra/l1/tools && npm ci
   KEY_FILE=~/.avalanche-cli/key/zyrcle-pchain.pk node import-atomic.mjs P-fuji1n3qzgzxfxjk05qss6hjvgmhd94wa3tvsw0ygch --dry-run
   KEY_FILE=~/.avalanche-cli/key/zyrcle-pchain.pk node import-atomic.mjs P-fuji1n3qzgzxfxjk05qss6hjvgmhd94wa3tvsw0ygch
   ```
3. **Check the chain afterwards** with the read-only smoke test. `ADMIN_ADDRESS` must be the
   precompiles' admin, which since 2026-11-23 is the Safe; with the old L1 admin address the admin
   checks now fail:
   ```bash
   ADMIN_ADDRESS=0x607c011C6921eA75C1e38223a5E5514eDbA7E43b \
     infra/l1/scripts/smoke-test.sh https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc
   ```
   It prints the height. ZyrcleChain makes blocks only when there are transactions, so on a quiet
   chain the height does not grow between two runs; it must grow after one (for example a small
   `chain fund`).

**Gap:** the repository does not record the exact `platform-cli` command that adds balance, the
validation ID it needs (the L1 runbook keeps it in the CLI sidecar
`~/.avalanche-cli/subnets/zyrcle/sidecar.json`, not in `fuji.env`), the fee rate, or how to read
the current balance. AvalancheGo v1.15 removed `platform.getBalance`. Check `platform-cli --help` on
the VPS, then record the command and the new run-out date here and as an amendment to ADR 0021.

### 9.9 The API is unhealthy

Work down this list.

1. **Container state.**
   ```bash
   docker compose -f deploy/compose.yml ps
   ```
   Docker marks `api` unhealthy after five failed checks. Nothing in the repository restarts it on
   that signal; `restart: unless-stopped` acts only when the process exits. Restart it by hand with
   `docker compose -f deploy/compose.yml restart api`.
2. **The health endpoint.**
   ```bash
   curl -s https://zyrcle-backend.deviego.xyz/health
   ```
   - `{"ok":true,"mqtt":true}`: the API and its database work.
   - `"mqtt":false`: the broker is down or refuses the API's password. Go to step 5.
   - An error or no answer: the database is unreachable (go to step 4), or the API is not running
     (step 3), or Traefik cannot route to it. Traefik's configuration is not in this repository;
     check that `api` is running and attached to `edge`.
3. **API logs.**
   ```bash
   docker compose -f deploy/compose.yml logs --tail 200 api
   ```
   - At startup it exits if `JWT_SECRET` is shorter than 32 characters, `OPERATOR_TOKEN` shorter
     than 24, or a key file is missing or unreadable. `ORACLE_KEY_PATH` and `OPERATOR_KEY_PATH` must
     be files that `DEPLOY_UID` can read.
   - A failing background job logs `periodic job <name> failed`. Names: `sweep`,
     `collection-sweep`, `codes`, `notifications`, `payouts`, `settlements`, `anchors`, `alerts`,
     `relays`, `recoveries`, `emails`.
4. **Postgres.**
   ```bash
   docker compose -f deploy/compose.yml ps postgres
   docker compose -f deploy/compose.yml logs --tail 200 postgres
   ```
   Its memory limit is 384 MB.
5. **Mosquitto.**
   ```bash
   docker compose -f deploy/compose.yml logs --tail 200 mosquitto
   ```
   `deploy/mosquitto/passwd` and `acl.runtime` must exist, `0600`, owned by `DEPLOY_UID`. Running
   `deploy.sh` again regenerates them; then restart Mosquitto.
6. **Payments stall but the API is healthy.** Look at the chain.
   ```bash
   docker compose -f infra/l1/node/compose.yml ps
   docker compose -f infra/l1/node/compose.yml logs --tail 200 node
   infra/l1/scripts/zyrcle-api-docker.sh chain state
   ```
   - The health report (`GET /v1/operator/health`, runbook 9.11) gives the last block's age, how
     long work has waited for the chain and the node's own health. A height that does not grow
     while transactions wait means the chain is halted; a quiet chain makes no blocks at all
     ([ADR 0028, amendment](adr/0028-pilot-readiness.md#amendments)). An empty validator balance
     halts it ([ADR 0021](adr/0021-l1-operations.md)).
   - `chain state` shows `available_cop`. At zero, the Treasury refuses to mint (`UnbackedMint`). The
     settlement worker waits 10 minutes on that refusal and on a paused Treasury
     ([ADR 0013](adr/0013-sale-and-settlement.md)).
7. **Memory.** `docker stats --no-stream` shows each container against its limit
   ([section 4.5](#45-memory-budget)).

### 9.10 Back up and restore the database

[ADR 0028](adr/0028-pilot-readiness.md). On the VPS:

```bash
~/apps/zyrcle/deploy/backup.sh                       # dump now into ~/backups/zyrcle, keep 14 days
~/apps/zyrcle/deploy/backup.sh --check FILE          # restore FILE into a throwaway Postgres, count rows
```

Daily from cron, installed on 2026-11-23 with Diego's approval: `15 3 * * *
$HOME/apps/zyrcle/deploy/backup.sh >> $HOME/backups/zyrcle/backup.log 2>&1`. The VPS runs in UTC,
so it fires at 22:15 Colombia time. Check it with `crontab -l` and `tail ~/backups/zyrcle/backup.log`.
`BACKUP_DIR` and `BACKUP_KEEP_DAYS` change the folder and the retention. Every `deploy.sh` run also
takes a dump before migrating.

To restore production from a dump, stop the API first so nothing writes meanwhile:

```bash
cd ~/apps/zyrcle/deploy
docker compose stop api
docker compose exec -T postgres psql -U zyrcle -d postgres -c "DROP DATABASE zyrcle" -c "CREATE DATABASE zyrcle OWNER zyrcle"
gunzip -c FILE | docker compose exec -T postgres psql -U zyrcle -d zyrcle -v ON_ERROR_STOP=1
docker compose start api
```

**Off-site, encrypted** ([ADR 0034](adr/0034-encrypted-off-site-backups.md)). `deploy/offsite.sh`
encrypts the newest dump with `age` to a public key and streams it to an S3-compatible bucket
(Cloudflare R2) with `rclone`; on Sundays, or with `--keys`, it also sends a bundle of the validator
identity (`staking/` from the node's volume, not the chain data), the key files and `deploy/.env`.
Both tools run in a container built from `deploy/offsite/Dockerfile`, so nothing is installed on the
host. The script never deletes remote copies: the bucket's lifecycle rule expires them (30 days for
dumps, 12 weeks for key bundles, per ADR 0034) and its lock keeps them from early deletion. Without
its five `OFFSITE_*` settings it says so and exits; on 2026-11-23 the bucket and the age key did not
exist yet.

```bash
~/apps/zyrcle/deploy/offsite.sh            # the newest dump now (and the keys bundle on Sundays)
~/apps/zyrcle/deploy/offsite.sh --keys     # the keys bundle now
```

Cron, once configured and approved: `40 3 * * * $HOME/apps/zyrcle/deploy/offsite.sh >>
$HOME/backups/zyrcle/offsite.log 2>&1`, after the dump at 03:15.

**Restore drill**, on Diego's machine, which holds the private key:

1. Download the newest `db/…sql.gz.age` from the bucket (R2 dashboard or `rclone`).
2. Decrypt it: `age -d -i zyrcle-backups.key FILE.sql.gz.age > FILE.sql.gz`.
3. Check it restores: copy it to any machine with Docker and run `deploy/backup.sh --check FILE.sql.gz`.

The keys bundle decrypts the same way into a `.tar.gz` with `keys/`, `node/staking/` and
`deploy.env`. CI proves the whole path on every push with `deploy/offsite-selftest.sh` (an S3
stand-in and a throwaway key).

### 9.11 Health and alerts

`GET /v1/operator/health` (and the console's summary) reports each outbox, devices online, the
broker, the chain's latest block and its age, the Treasury's mintable pesos and the gas of the oracle
and operator keys. Each warning is emailed to every active admin at most once a day. Thresholds are
settings (`alert_*` in [config.py](../apps/api/src/zyrcle_api/config.py)): queue stuck 30 min, any
failed row, no block for 10 min while a transaction has waited for the chain as long, the validator
node reporting itself unhealthy, under 100,000 COP mintable, under 1 ZYR of gas. ZyrcleChain makes
no empty blocks, so a quiet night leaves the last block hours old without anything being wrong.

From outside the VPS ([ADR 0033](adr/0033-error-reports-and-uptime.md)):

- **Uptime.** [.github/workflows/uptime.yml](../.github/workflows/uptime.yml) checks every 10 minutes
  that the API answers and is connected to the broker, that the web app answers and that the public
  RPC answers. A failure opens a GitHub issue labelled `uptime` (GitHub notifies the owner), later
  failures comment on it, and the first healthy check closes it. Run it by hand from the Actions
  tab. GitHub pauses scheduled workflows after 60 days without activity in the repository.
- **Error reports.** With a Sentry DSN, the API, the web app and the mobile app report unhandled
  errors and every logged exception, with the commit or app version. Reports are scrubbed before
  they leave: no emails, keys, tokens, request bodies, cookies or headers.

### 9.12 Top up gas for the backend's keys

The oracle key (advances, and as guardian it relays payments and deploys accounts) and the operator
key (sales, settlements, certificate anchors) pay gas in ZYR, and so will a separate guardian key
after runbook 9.13. The health report warns under 1 ZYR (runbook 9.11). Send gas from the L1
admin's float (about 48 ZYR after the handover; the key holds no admin power):

```bash
infra/l1/scripts/zyrcle-api-docker.sh chain balance --address 0xfdDD10F3BB701dCB21bF711bf3d28f96FA9a2f7d
infra/l1/scripts/zyrcle-api-docker.sh chain fund --from-key-file /keys/zyrcle-l1-admin.pk \
  --to 0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50 --amount-zyr 20      # oracle
infra/l1/scripts/zyrcle-api-docker.sh chain fund --from-key-file /keys/zyrcle-l1-admin.pk \
  --to 0x528815e03Aa80b045B32840f3e26B394D0838d0d --amount-zyr 20      # operator
```

It is a transaction on Fuji and needs Diego's approval. The float is finite. The Safe, as the
NativeMinter's admin, could mint more gas, but that would create ZYR without backing, so it is not
done.

### 9.13 Give the guardian its own key

The AccountFactory guardian starts lost-phone recoveries and relays signed payments (ADR 0010,
0029). It shares the oracle key; [ADR 0040](adr/0040-keys-guardian-and-multisig.md) gives it its
own.
`deploy.sh` points `GUARDIAN_KEY_PATH` at the oracle key until this runbook runs, and on
2026-11-23 it had not run yet. It is a Fuji transaction and needs Diego's approval. Since the
handover the Safe names the guardian, so two owners sign the proposal (runbook 9.14). The checkout
must include commit `fd05fa7`, which added `--what guardian`.

```bash
cd ~/apps/zyrcle && source infra/l1/fuji.env
W=infra/l1/scripts/zyrcle-api-docker.sh
$W keys new --out /keys/zyrcle-guardian.pk          # prints only the new address
$W chain fund --from-key-file /keys/zyrcle-l1-admin.pk --to <new address> --amount-zyr 10
# One proposal, two calls: the new guardian on the deployer allow list, then named in the factory.
$W safe propose --safe $SAFE --what guardian --guardian <new address> --multisend $SAFE_MULTISEND \
   --out ../../infra/l1/safe/3-guardian.json
# Two owners sign infra/l1/safe/3-guardian.json (runbook 9.14), then:
$W safe exec --proposal ../../infra/l1/safe/3-guardian.json --key-file /keys/zyrcle-l1-admin.pk
sed -i "s|^GUARDIAN_KEY_PATH=.*|GUARDIAN_KEY_PATH=$HOME/.avalanche-cli/key/zyrcle-guardian.pk|" deploy/.env
git checkout <deployed sha>                         # deploy.sh wants the deployed commit
deploy/deploy.sh <deployed sha> <deployed web sha>  # the API now relays with the new key
git checkout main
```

Record the address in `infra/l1/fuji.env` (`ACCOUNT_GUARDIAN`) and in the offline inventory, and
commit the executed proposal. The health report then shows the guardian's gas next to the oracle's
and the operator's. Recoveries already started by the old guardian finish normally: the account
checks the guardian when a recovery starts, not later. The oracle key stays on the
ContractDeployerAllowList; the proposal does not remove it.

### 9.14 Make an admin change through the Safe

[ADR 0040](adr/0040-keys-guardian-and-multisig.md). Since 2026-11-23 every admin power of
ZyrcleChain belongs to the Safe `0x607c011C6921eA75C1e38223a5E5514eDbA7E43b`: two of its three
owners (Diego's Core wallet, his phone's MetaMask and a paper key, section 6.1) must sign each
change, an emergency pause included. Every change is a Fuji transaction and needs Diego's approval.
Commands run on the VPS through the wrapper (`W=infra/l1/scripts/zyrcle-api-docker.sh`, after
`source infra/l1/fuji.env` for `SAFE` and `SAFE_MULTISEND`), from a checkout that includes commit
`fd05fa7` for `--what guardian` and `--what call`.

| Change | Proposal |
|---|---|
| A new AccountFactory guardian | `--what guardian` (runbook 9.13) |
| Pause or unpause the Treasury, move a Treasury role | `--what call --to $TREASURY` (runbook 9.4) |
| Retire a Treasury from the NativeMinter | `--what call` with `setNone(address)` on `0x0200…0001` (runbook 9.6) |
| Allow or remove a contract deployer | `--what call` with `setEnabled(address)` or `setNone(address)` on `0x0200…0000` |
| Fees, the reward address, the validator set, a Safe owner | `--what call`; the repository has no procedure for these yet |

1. **Propose.** `--function` is the signature and `--args` its arguments, in order; the command
   encodes the call itself, so no other tool is needed on the VPS. A `bytes32` argument that is not
   hex is hashed as text (`OPERATOR_ROLE` gives the role id). `--data 0x…` takes ready calldata
   instead. `--description` says in plain words what it does. The command prints the description and the
   Safe's hash for the transaction, and writes the proposal file:
   ```bash
   $W safe propose --safe $SAFE --what call --to <contract> --function '<name>(<types>)' --args <…> \
     --description "<what it does>" --out ../../infra/l1/safe/<n>-<name>.json
   ```
2. **Two owners sign**, each adding a signature to the same file:
   - With a wallet: open `https://zyrcle.deviego.xyz/multisig` in the browser that has it (a
     browser extension, or the browser inside the phone's wallet app), load or paste the proposal,
     press "Firmar con mi billetera", then "Descargar propuesta" or "Copiar", and pass the signed
     file on. The page adds the ZyrcleChain network to the wallet the first time.
   - With the paper key, on a computer with the API installed:
     `ZYRCLE_CHAIN_RPC_URL=<public RPC URL> apps/api/.venv/bin/zyrcle-api safe sign --proposal FILE
     --key-file -`. It asks for the key without showing it or writing it anywhere.

   The page and the command check that each signature is an owner's over that exact proposal; the
   Safe checks again on chain.
3. **Execute** from the VPS. The key file only pays the gas; today the L1 admin key's float does:
   ```bash
   $W safe exec --proposal ../../infra/l1/safe/<n>-<name>.json --key-file /keys/zyrcle-l1-admin.pk
   ```
   It refuses a proposal whose hash does not match the Safe's, or whose nonce the Safe has passed:
   proposals run one at a time, so make the next one only after this one has run.
4. **Record it.** Commit the executed proposal in [infra/l1/safe/](../infra/l1/safe/README.md) and
   update `fuji.env` and this document if an address or a role changed. `$W safe status --safe
   $SAFE --admin <address>` shows, for each power, whether an address and the Safe hold it.

**The handover, 2026-11-23.** With Diego's approval the L1 admin key deployed the Safe and its
helper contracts (`safe deploy`, owners above, threshold 2) and moved its eight powers in five
steps that kept a way back until the end: `safe grant` (the Safe gets every role and precompile
admin too), `safe propose --what proof` signed by two owners and executed
([1-proof.json](../infra/l1/safe/1-proof.json)), `safe own` (the validator manager and its proxy
admin), `safe propose --what revoke` signed and executed
([2-revoke.json](../infra/l1/safe/2-revoke.json): the Safe takes the admin key off the four
precompiles in one MultiSendCallOnly batch), and `safe renounce` (the admin key gives up its
Treasury and AccountFactory roles). Checked on the public RPC afterwards: the Safe holds the eight
powers, the L1 admin key none, and the Treasury still mints (ADR 0040, amendment). A new chain
repeats these commands with its own admin key. Still pending: the admin key leaves the VPS once its
gas float has another holder (runbook 9.12).

## 10. Known gaps and risks

Each item is checked against the repository.

**Data and availability**

- **The API image takes the newest version of each Python dependency.** `apps/api/pyproject.toml`
  sets lower bounds and the Dockerfile installs with `pip`, with no lock file, so a new major version
  of a library reaches production with the next image. On 2026-11-26 sentry-sdk 3.0.1 did, and the
  API crashed on start once its Sentry DSN was set ([ADR 0033](adr/0033-error-reports-and-uptime.md),
  amendments). Sentry is now capped below 3. The fix for the rest is built and waits for its
  deploy: the image installs `apps/api/requirements.txt`, exact versions with hashes, written by
  `apps/api/scripts/lock.sh` ([ADR 0044](adr/0044-api-dependencies-locked.md)). The web and mobile
  apps install from `package-lock.json` and are not affected.

- **Off-site copies wait for their bucket.** `deploy/offsite.sh` copies the dumps, the validator
  identity, the key files and `deploy/.env` off the VPS, encrypted (runbook 9.10), and CI proves the
  path. It does nothing until Diego sets up the bucket and the age key; until then every copy stays
  on the machine. Its cron entry is not installed.
- **A rollback across a migration loses data.** `deploy.sh` backs up the database before migrating,
  so a bad migration is undone by restoring that dump (runbook 9.10), losing what was written since;
  a downgrade drops the newer tables instead (runbook 9.2).
- **One VPS.** It runs the application, the validator and Traefik, shared with other projects. It is
  a single point of failure for the demo and the chain ([ADR 0020](adr/0020-single-vps-docker-compose.md)).
  The memory limits add up to 4,160 MiB on a 4 GB machine ([section 4.5](#45-memory-budget)).
- **One validator.** It is a single point of failure for the chain. ADR 0002 accepts that on
  testnet; ADR 0021 asks for a second validator before any real value moves.
- **Validator fee deadline.** The balance lasts until about 2027-03-09. Topping it up is manual,
  with the P-Chain key, and its exact command is not recorded
  ([runbook 9.8](#98-top-up-the-validator)).
- **Testnet only.** ZyrcleChain runs on Fuji. ZYR has no value and the seed capital is simulated
  ([ADR 0023](adr/0023-testnet-economics.md)). The chain for real value is an open M7 decision.
- **Monitoring has limits.** The health report emails admins (runbook 9.11) and the uptime workflow
  watches from outside, and Sentry has collected errors since 2026-11-26, but GitHub may delay a
  scheduled check by some minutes and pauses it after 60 days without repository activity, the
  Grafana that ADR 0002 mentions is configured outside this repository, and an unhealthy container
  is not restarted on its own.

**Chain and keys**

- **Gas is a finite float.** The operator and oracle keys pay gas from the L1 admin's 100-ZYR
  genesis float: about 5 ZYR each on 2026-11-22 and 20 more each on 2026-11-23 (runbook 9.12),
  leaving the admin key about 48 ZYR after the handover. At the 2026-11-22 gas price (175 gwei) a
  payout or settlement transaction costs a few hundredths of a ZYR. Nothing refills them
  automatically; the health report warns under 1 ZYR, and the Treasury cannot mint gas for its own
  keys.
- **Hot keys on the server.** The oracle and operator keys sit on the VPS and are mounted into the
  API ([ADR 0013](adr/0013-sale-and-settlement.md)). The oracle key is also the guardian and is on
  the deployer allow list: compose mounts a separate `guardian.key`, but `GUARDIAN_KEY_PATH` still
  points at the oracle key until runbook 9.13 runs.
- **The L1 admin key is still on the VPS.** It holds no admin power, only the gas float; ADR 0040
  moves it off once the float has another holder.
- **Admin changes need two of three signers.** Since 2026-11-23 the Safe holds every admin power
  (runbook 9.14); an emergency pause of the Treasury also needs two signatures and a few minutes.
  Losing two of the three owner keys would lock these powers for good.
- **Admin commands lag behind the Safe.** No command builds the calldata of a role change, a pause
  or an allow-list edit; it is built by hand for `safe propose --what call`. `chain deploy` and
  `chain accounts-deploy` cannot finish since the handover, so redeploying the Treasury or the
  factory is not scripted (runbook 9.6). No command tops up the validator, changes fees or the reward address,
  or replaces a Safe owner.
- **The P-Chain key is a single key on the VPS.** It funds the validator and is not an EVM account,
  so it cannot move to the Safe. ADR 0040 meant it to stay offline; its amendment records that it is
  still in `~/.avalanche-cli/key/`, and moving it offline between top-ups is Diego's to decide.
- **RewardManager** has no reward address, although ADR 0002 says fees go to the treasury.

**Deployment**

- **Manual deploys, no scripted rollback across migrations.** `deploy.sh` checks the checkout, pins
  the images by digest and records every deploy in `deploy/history.log` (ADR 0032), but a rollback
  across a migration is still done by hand (runbook 9.2).
- **Traefik, the `edge` network, TLS certificates and DNS** are configured outside this repository.
- **Whether the GHCR images are public or private** is not recorded. If they are private, the VPS
  needs a `docker login ghcr.io`, which is not in the repository.
- **CI's service images float.** Production and the base images are pinned by digest, with
  Dependabot proposing updates (ADR 0032), but the `api` and `e2e` jobs start `postgres:17-alpine`
  and `eclipse-mosquitto:2` by tag. `deploy/offsite/Dockerfile` pins Alpine by digest but is not in
  Dependabot's list.
- **Hardening is partial.** `postgres` and `migrate` are not hardened and `migrate` has no memory
  limit.
- **The `internal` network is not isolated.** It is not marked `internal: true`, so Postgres,
  Mosquitto and the simulator can reach the internet. Any container on the `edge` network, which
  Traefik also uses, can reach the node's HTTP API on 9650.

**Devices and email**

- **The broker has no TLS and is not published.** ADR 0005 and [device-protocol.md](device-protocol.md)
  call for MQTT over TLS in production. Today only the simulator connects, inside the VPS. A
  physical container needs a published TLS listener, which is not in the repository.
- **Email is optional in compose but required in practice.** Without `RESEND_API_KEY`, operators
  cannot sign in, residents cannot recover accounts and admins get no alerts. Production has one
  (reported on 2026-11-23; the repository cannot show it).

**Mobile**

- **Mobile builds are manual** and outside CI (ADR 0015). No iOS build and no store submission are
  recorded.

**Documentation drift found while writing this**

- `deploy/.env.example` says it is "Generated by bootstrap.sh"; the script is `deploy.sh`.
- The header of `deploy/backup.sh` says copying the dumps elsewhere is "a separate, pending
  decision"; ADR 0034 made it and `deploy/offsite.sh` does it.
- `smoke-test.sh`'s own usage text and its `admin` checks assume the precompiles' admin is a key;
  since the handover, read-only mode with the Safe's address is the only one that passes
  (runbook 9.8).
