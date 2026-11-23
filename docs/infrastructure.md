# Zyrcle infrastructure

This document describes how Zyrcle runs in production, how it is built and released, and how to
operate or rebuild it. It is written for the engineer who keeps it running.

> Checked against commit `15df50e` (2026-11-22) and the decision records written the same day.
> Every statement comes from a file in this repository. When something is not in the repository,
> this document says so.

Shorter, component-level guides: [deploy/README.md](../deploy/README.md),
[infra/l1/README.md](../infra/l1/README.md), [chain/README.md](../chain/README.md),
[apps/mobile/README.md](../apps/mobile/README.md). Running the code on a laptop:
[repository.md](repository.md). The decisions behind this setup:
[ADR 0020](adr/0020-single-vps-docker-compose.md) (one VPS),
[ADR 0021](adr/0021-l1-operations.md) (L1 operations) and
[ADR 0022](adr/0022-keys-secrets-and-production-changes.md) (keys and who may change production).

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
| AccountFactory, guardian | The contract that creates residents' smart accounts, and the backend key that may start an account recovery ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). |
| Outbox | A table that a database transaction writes to. A worker sends its rows to the outside world. |

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
  api -->|"edge: JSON-RPC to zyrcle-l1-node-1:9650"| l1node
  keys -.->|"oracle.key and operator.key, read-only"| api
  peers <-->|"P2P 9651, published"| l1node

  api -->|"HTTPS"| expo["Expo push service"]
  expo --> fcm["FCM for Android<br/>APNs for iOS"]
  fcm --> users
  api -->|"HTTPS"| resend["Resend email API"]

  gha["GitHub Actions<br/>CI and Release images"] -->|"push images"| ghcr[("GHCR<br/>ghcr.io/diegowritescode")]
  ghcr -.->|"docker compose pull in deploy.sh"| api
  ghcr -.->|"docker compose pull in deploy.sh"| web
  eas["EAS Build, Expo cloud"] -->|"APK or AAB"| users
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
  capital is simulated ([ADR 0023](adr/0023-testnet-economics.md)).
- **Secrets.** `deploy/.env` exists only on the VPS. Private keys are files in
  `~/.avalanche-cli/key/` on the VPS ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)).
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

CI runs on GitHub-hosted Ubuntu runners with Python 3.13 and Node 22. Only the `api` job starts
services:

- **Postgres** `postgres:17-alpine` as a job service on port 5432 (user, password and database
  `zyrcle`).
- **Mosquitto** `eclipse-mosquitto:2`, started with `docker run`, using the development
  configuration, ACL and password file.
- **anvil** from Foundry v1.5.1. The pytest fixture starts it on a free port with chain ID
  20261121. Chain tests skip when anvil is missing.

Tests read `ZYRCLE_TEST_DATABASE_URL` and `ZYRCLE_TEST_MQTT_HOST` to point elsewhere. CI never
deploys. [Section 8](#8-cicd) lists every job.

## 4. Production services

### 4.1 Settings shared by the services

- **Image tags.** `api`, `migrate` and `sim` run `ghcr.io/diegowritescode/zyrcle-api:${ZYRCLE_API_TAG}`.
  `web` runs `ghcr.io/diegowritescode/zyrcle-web:${ZYRCLE_WEB_TAG}`. Both tags are full commit
  SHAs. `deploy.sh` rejects any tag that is not 40 hexadecimal characters. `latest` is never used
  ([ADR 0020](adr/0020-single-vps-docker-compose.md)).
- **Logging.** The `x-logging` anchor keeps Docker's JSON log files at 10 MB, three files per
  container. `migrate` does not use it.
- **Hardening.** The `x-hardened` anchor sets a read-only root filesystem, a `tmpfs` at `/tmp`, drops
  every Linux capability and sets `no-new-privileges`. `mosquitto`, `api`, `sim` and `web` use it.
  `postgres` and `migrate` do not, although [deploy/README.md](../deploy/README.md) says every
  container is hardened.
- **Restart policy.** Every long-running service has `restart: unless-stopped`.
- **The backend image** ([apps/api/Dockerfile](../apps/api/Dockerfile)) builds in two stages from
  `python:3.13-slim`. It installs `packages/protocol`, `device/simulator[control]` and `apps/api`
  into a virtualenv, copies `alembic.ini` and the migrations, and runs as user `zyrcle` (UID 10001).
  Its default command is `zyrcle-api serve --host 0.0.0.0 --port 8000`. The same image runs the
  simulator.
- **The web image** ([apps/web/Dockerfile](../apps/web/Dockerfile)) builds the Vite app with
  `node:22-alpine` and serves it with `nginxinc/nginx-unprivileged:1.29-alpine` on port 8080. The
  `VITE_*` values are baked in at build time ([section 5.4](#54-web-and-mobile-build-time-settings)).

### 4.2 Each service

**postgres**
- Image `postgres:17-alpine`. Default command. No published port.
- Volume `pgdata` at `/var/lib/postgresql/data`. Network `internal`.
- Health check `pg_isready -U zyrcle -d zyrcle` every 10 s, 5 retries.
- Memory limit 384 MB. Not hardened.

**mosquitto**
- Image `eclipse-mosquitto:2.1.4-alpine`. Entrypoint `/usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf`.
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
- Mounts `${ORACLE_KEY_PATH}` at `/run/secrets/oracle.key` and `${OPERATOR_KEY_PATH}` at
  `/run/secrets/operator.key`, both read-only.
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
  | Settlements (sales) | the above plus the operator key |
  | Recoveries | the above plus the AccountFactory address |
  | Emails | a Resend key is set, or log-only mode |

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
  `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self' https://zyrcle-backend.deviego.xyz wss://zyrcle-backend.deviego.xyz https://rpc.zyrcle.deviego.xyz; img-src 'self' data: https://images.unsplash.com; media-src 'self' data: blob: mediastream:; style-src 'self' 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.
  The production domains are written into it. A domain change needs an edit here and a new image.

### 4.3 Start order

```
postgres (healthy) ─► migrate ─► sim (keys created) ─► demo seed ─► api, web
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
| `ZYRCLE_OPERATOR_KEY_FILE` | none | `/run/secrets/operator.key` | the file is | Path to the hex private key with the Treasury's OPERATOR_ROLE. Without it, confirmed sales wait. |
| `ZYRCLE_SETTLEMENT_INTERVAL_S` | `3.0` | default | no | Settlement worker interval. |
| `ZYRCLE_ADVANCE_RATIO_BPS` | `5000` | default | no | Advance as a share of the reference price, in basis points (50 %, [ADR 0023](adr/0023-testnet-economics.md)). |
| `ZYRCLE_MAX_ADVANCE_COP` | `5000` | default | no | Advance cap per deposit, as in the contract. |
| `ZYRCLE_PAYOUT_INTERVAL_S` | `2.0` | default | no | Payout worker interval. |
| `ZYRCLE_PUSH_ENABLED` | `true` | default | no | Turns the push notification worker on. |
| `ZYRCLE_EXPO_PUSH_URL` | `https://exp.host/--/api/v2/push` | default | no | Expo push API base URL. |
| `ZYRCLE_EXPO_ACCESS_TOKEN` | none | `${EXPO_ACCESS_TOKEN:-}` | yes | Needed only if "enhanced security for push notifications" is on in Expo ([ADR 0008](adr/0008-push-notifications.md)). |
| `ZYRCLE_NOTIFICATION_INTERVAL_S` | `2.0` | default | no | Push worker interval. |
| `ZYRCLE_PUSH_RECEIPT_DELAY_S` | `900` | default | no | When to ask Expo for delivery receipts (15 min). |
| `ZYRCLE_ACCOUNT_FACTORY_ADDRESS` | none | `${ACCOUNT_FACTORY:-}` | no | AccountFactory address. Empty turns smart accounts and recovery off ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). |
| `ZYRCLE_GUARDIAN_KEY_FILE` | none, falls back to the oracle key | not set | the file is | Key that starts and cancels recoveries. Compose does not set it, so production uses the oracle key. |
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
and email.

### 5.2 `deploy/.env`

`deploy.sh` creates `deploy/.env` from [deploy/.env.example](../deploy/.env.example) the first time,
with fresh secrets. It never adds a variable that appears later in `.env.example`; add those by
hand. The header of `.env.example` says "Generated by bootstrap.sh"; the script is `deploy.sh`.

| Variable | Value in `.env.example` or how it is set | Secret | Used for |
|---|---|---|---|
| `ZYRCLE_API_TAG` | written by every `deploy.sh` run | no | Backend image tag (full SHA). |
| `ZYRCLE_WEB_TAG` | written by every `deploy.sh` run | no | Web image tag (full SHA). |
| `API_HOST` | `zyrcle-backend.deviego.xyz` | no | Traefik rule for `api`. |
| `WEB_HOST` | `zyrcle.deviego.xyz` | no | Traefik rule for `web`, SIWE domain, CORS origin. |
| `BLOCKCHAIN_ID` | `hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8` | no | Builds the RPC URL. |
| `TREASURY` | `0xd7052201140224018b123ecFF7b83B4251790Aeb` | no | Treasury address. |
| `ORACLE_KEY_PATH` | `$HOME/.avalanche-cli/key/zyrcle-oracle.pk` (set by `deploy.sh`) | path only | Host file mounted as the oracle key. |
| `OPERATOR_KEY_PATH` | `$HOME/.avalanche-cli/key/zyrcle-operator.pk` (set by `deploy.sh`) | path only | Host file mounted as the operator key ([ADR 0013](adr/0013-sale-and-settlement.md)). |
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

`deploy.sh` also renames two legacy names in place: `ZYRCLE_DEMO_TAG` becomes `ZYRCLE_WEB_TAG` and
`DEMO_HOST` becomes `WEB_HOST`.

### 5.3 Other variables

| Variable | Where | Secret | What it does |
|---|---|---|---|
| `ZYRCLE_SIM_PASSWORD_<DEVICE>` (for example `ZYRCLE_SIM_PASSWORD_CTR_0001`), fallback `ZYRCLE_SIM_PASSWORD` | simulator | yes | Broker password per simulated container. |
| `SKIP_PULL=1` | `deploy.sh` | no | Skips `docker compose pull`. Local rehearsals only. |
| `RPC_PUBLIC`, `RPC_HOST`, `BLOCKCHAIN_ID` | `infra/l1/node/.env` (not committed) | no | Public RPC route. Defaults: `false`, `rpc.zyrcle.deviego.xyz`, `unset`. |
| `ZYRCLE_CHAIN_RPC_URL`, `ZYRCLE_TREASURY_ADDRESS`, `ZYRCLE_ACCOUNT_FACTORY_ADDRESS` | `zyrcle-api chain …` | no | The chain commands read only these. The wrapper script sets the first two from `infra/l1/fuji.env`. |
| `ADMIN_PRIVATE_KEY` or `ADMIN_ADDRESS`, `SMOKE_MINT` | `infra/l1/scripts/smoke-test.sh` | the key is | Full or read-only smoke test. `SMOKE_MINT=1` mints for real, local networks only. |
| `AVALANCHE_PRIVATE_KEY` | `platform-cli` | yes | Read from the key file in the shell, never typed as an argument. |
| `KEY_FILE`, `AVAX_URI` | `infra/l1/tools/import-atomic.mjs` | the file is | Finishes a stuck C-Chain to P-Chain transfer. |
| `ZYRCLE_TEST_DATABASE_URL`, `ZYRCLE_TEST_MQTT_HOST` | API tests | no | Point the tests at another database or broker. |
| `ANVIL_RPC` | `apps/api/dev/local_chain.py` | no | anvil URL, default `http://127.0.0.1:8545`. |
| `GOOGLE_SERVICES_JSON` | EAS environment variable, type file, visibility secret | yes | Path to Firebase's `google-services.json`, read by [app.config.ts](../apps/mobile/app.config.ts). |

### 5.4 Web and mobile build-time settings

Both clients bake their settings in at build time. A different deployment needs a new build.

| Web (`VITE_*`) | Mobile (`EXPO_PUBLIC_*`) | Production value | Must match |
|---|---|---|---|
| `VITE_API_URL` | `EXPO_PUBLIC_API_URL` | `https://zyrcle-backend.deviego.xyz` | `API_HOST` |
| `VITE_SIWE_DOMAIN` | `EXPO_PUBLIC_SIWE_DOMAIN` | `zyrcle.deviego.xyz` | `ZYRCLE_SIWE_DOMAIN` (`WEB_HOST`) |
| `VITE_CHAIN_ID` | `EXPO_PUBLIC_CHAIN_ID` | `20261121` | `ZYRCLE_CHAIN_ID` |
| `VITE_RPC_URL` | `EXPO_PUBLIC_RPC_URL` | the public RPC URL above | `BLOCKCHAIN_ID` |
| `VITE_TREASURY_ADDRESS` | none | `0xd7052201140224018b123ecFF7b83B4251790Aeb` | `TREASURY` |
| none | `EXPO_PUBLIC_ACCOUNT_FACTORY` | `0x0bE806Ca77340aA50AF6586CDC2FE2561668DaEA` | `ACCOUNT_FACTORY`, `infra/l1/fuji.env` |
| none | `EXPO_PUBLIC_WEB_URL` | `https://zyrcle.deviego.xyz` | `WEB_HOST` |

The web production values are `ARG` defaults in [apps/web/Dockerfile](../apps/web/Dockerfile); the
release workflow passes no build arguments. [apps/web/.env.example](../apps/web/.env.example) holds
local values. The mobile production values are the fallbacks in
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
  VPS and spending EAS builds all need Diego's explicit approval.

### 6.1 On-chain keys

| Key | Location | Public address ([fuji.env](../infra/l1/fuji.env)) | What it controls | If it leaks |
|---|---|---|---|---|
| L1 admin | `~/.avalanche-cli/key/zyrcle-l1-admin.pk` on the VPS | `0xfdDD10F3BB701dCB21bF711bf3d28f96FA9a2f7d` | Admin of the NativeMinter, ContractDeployerAllowList, FeeManager and RewardManager precompiles. Owner of the validator manager and its proxy. Admin (`DEFAULT_ADMIN_ROLE`) of the Treasury, because it deployed it, and of the AccountFactory. | The holder can mint ZYR directly: `smoke-test.sh` checks that the admin can mint. That bypasses the Treasury's backing rule ([ADR 0007](adr/0007-on-chain-treasury.md)). It can also change fees, allow any deployer, grant Treasury roles, replace the guardian and change the validator set. This is the most powerful key. The repository has no procedure to replace it. |
| P-Chain key | `~/.avalanche-cli/key/zyrcle-pchain.pk` on the VPS | `P-fuji1n3qzgzxfxjk05qss6hjvgmhd94wa3tvsw0ygch` (`PCHAIN_OWNER`) | Signs P-Chain transactions with `platform-cli`: subnet, chain, conversion to L1, validator balance ([ADR 0021](adr/0021-l1-operations.md)). Holds the test AVAX that funds the validator. | The holder can spend its test AVAX. What else it controls after the L1 conversion is not in the repository. |
| Treasury operator | `~/.avalanche-cli/key/zyrcle-operator.pk`, mounted into `api` at `/run/secrets/operator.key` | `0x528815e03Aa80b045B32840f3e26B394D0838d0d` | `OPERATOR_ROLE`: `recordSeedCapital`, `recordSale`, `setAdvanceLimits`. The backend uses it only after a named operator confirms the bank match ([ADR 0013](adr/0013-sale-and-settlement.md)). | The holder can record fake sales or seed capital and back new ZYR with them. The admin can revoke the role at once; every sale carries its evidence hash, and the bank reconciliation would not match (ADR 0013). It can also raise the advance limits (`setAdvanceLimits` in [Treasury.sol](../chain/src/Treasury.sol)). |
| Treasury oracle, also the AccountFactory guardian | `~/.avalanche-cli/key/zyrcle-oracle.pk`, mounted into `api` at `/run/secrets/oracle.key` | `0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50` | `ORACLE_ROLE`: `payAdvance`, `settleResidents`, `payCollector`, `payHost`. As guardian it starts and cancels recoveries. It is on the ContractDeployerAllowList so it can deploy accounts. | It can pay at most the daily cap per resident address until an admin pauses the Treasury; it cannot raise `backing` ([ADR 0007](adr/0007-on-chain-treasury.md)). It can start a recovery on any account, which takes effect after 48 hours unless the owner cancels ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). The factory admin can replace the guardian in one transaction (ADR 0010). A comment in `config.py` says production should give the guardian its own key; production does not yet. |
| Validator identity | Docker volume `zyrcle-l1_node-data` (`/data` in the node) | `NodeID-LEXURXpvabdwVCyUZeTUKLFPf2won5DXp` | Staking key, TLS certificate and BLS signer of the validator. | Losing it gives a new NodeID that is no longer the validator ([infra/l1/node/compose.yml](../infra/l1/node/compose.yml)). The repository does not discuss a leak. |
| Simulated container keys | Docker volume `zyrcle_sim-keys`, files `ctr-000N.pem` | none | Sign each simulated container's messages ([device-protocol.md](device-protocol.md)). | The holder can forge that container's readings, and so deposits and advances. Deleting the volume makes new keys; the next `deploy.sh` registers them (`demo seed` updates changed public keys). |

The oracle and operator keys pay gas in ZYR. They were funded by hand from the L1 admin's genesis
float (100 ZYR): on 2026-11-22 the operator held about 4.97 ZYR, the oracle about 4.80 and the admin
about 88.95 (read from the public RPC). No script funds them; see section 10.

### 6.2 Secrets in `deploy/.env`

| Secret | What it is for | If it leaks |
|---|---|---|
| `POSTGRES_PASSWORD` | The database user's password. Postgres is reachable only on `internal`. | Read and write every table, for someone who can reach the database. |
| `JWT_SECRET` | Signs resident and operator sessions; keys the HMAC of email codes ([operator_auth.py](../apps/api/src/zyrcle_api/operator_auth.py), [recovery.py](../apps/api/src/zyrcle_api/recovery.py)). | The holder can forge a session for any resident or operator, admins included. |
| `OPERATOR_TOKEN` | Shared machine token; acts as admin `token` ([ADR 0014](adr/0014-operator-accounts.md)). | Every operator action: add admins, approve deposits, record and confirm sales. A confirmed sale makes the backend record it on chain with the operator key. ADR 0014 says to rotate it once operators have their own accounts. |
| `MQTT_API_PASSWORD` | The API's broker account. | Read every device's uplink and send commands (`display`, `unlock`, `lock`) to any container. Commands are not signed ([device-protocol.md](device-protocol.md)). The broker is not published outside the VPS. |
| `MQTT_CTR_0001_PASSWORD` … `0004` | Each simulated container's broker account. | Publish on that container's topics. Messages still need the device's signature, so the password alone cannot forge readings. |
| `EXPO_ACCESS_TOKEN` (optional) | Expo push with enhanced security ([ADR 0008](adr/0008-push-notifications.md)). | Send push notifications through the project, when enhanced security is on. |
| `RESEND_API_KEY` (optional) | Sends email for the verified domain. | Send email as `no-reply@zyrcle.deviego.xyz` and use up the daily quota ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). |
| `PINATA_JWT` (optional) | Pins impact certificates on IPFS ([ADR 0027, amendment](adr/0027-impact-certificates.md#amendments)). | Pin or, if the key allows it, unpin files in Zyrcle's Pinata account and use up its quota. It cannot change a pinned file: a CID is its content's hash. |

Files derived from these: `deploy/mosquitto/passwd` (hashed broker passwords) and
`deploy/mosquitto/acl.runtime`. Both are `0600` and ignored by git.

### 6.3 External accounts and credentials

| Credential | Where it lives | Notes |
|---|---|---|
| `GITHUB_TOKEN` | Issued by GitHub Actions for each run | The release workflow uses it to push to GHCR (`packages: write`). The workflows use no other repository secret. |
| Expo account and EAS project | `@diegowritescode/zyrcle`, project ID in [app.json](../apps/mobile/app.json) | Builds run on EAS ([ADR 0015](adr/0015-android-builds.md)). |
| `GOOGLE_SERVICES_JSON` | EAS secret file variable (environments development, preview, production) and Diego's private folder | Firebase project `zyrcle-18c69`, app `xyz.deviego.zyrcle`. Kept out of git by [apps/mobile/.gitignore](../apps/mobile/.gitignore). |
| FCM v1 service-account key | EAS credentials and Diego's private folder | Lets EAS and Expo deliver Android push through Firebase ([ADR 0015](adr/0015-android-builds.md)). |
| Android signing keystore | Held by Expo | Signs the APKs and app bundles ([ADR 0015](adr/0015-android-builds.md)). |
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

The L1 admin (`0xfdDD…2f7d`) is the admin of every allow-list precompile ([genesis.fuji.json](../infra/l1/genesis.fuji.json)).

| Precompile | Address | What Zyrcle uses it for |
|---|---|---|
| ContractDeployerAllowList | `0x0200000000000000000000000000000000000000` | Only listed addresses deploy contracts. The guardian (oracle key) is listed so it can deploy smart accounts on their first recovery. |
| NativeMinter | `0x0200000000000000000000000000000000000001` | The Treasury is the enabled minter. The admin can also mint. |
| FeeManager | `0x0200000000000000000000000000000000000003` | Enabled; fees are set in genesis. |
| RewardManager | `0x0200000000000000000000000000000000000004` | Enabled. ADR 0002 says fees go to the treasury. The genesis sets no reward address, and no script in the repository sets one. |
| Warp | `0x0200000000000000000000000000000000000005` | Enabled from genesis for a future bridge. The L1's own validators sign P-Chain Warp messages (`requirePrimaryNetworkSigners: false`). |

Foundry scripts cannot call Subnet-EVM precompiles, which is why contracts are not deployed with
`forge script` ([chain/README.md](../chain/README.md)).

### 7.3 Validator

- One validator, `NodeID-LEXURXpvabdwVCyUZeTUKLFPf2won5DXp`, weight 100, on the VPS
  ([section 4.4](#44-the-l1-node-project-zyrcle-l1)).
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
| Treasury | `0xd7052201140224018b123ecFF7b83B4251790Aeb` | [Treasury.sol](../chain/src/Treasury.sol) with the host share and redemptions, deployed 2026-11-23 with `zyrcle-api chain deploy` ([ADR 0029](adr/0029-closed-loop-payments.md)) |
| Second Treasury (no longer used) | `0xBc5035341C075CBd75508ff1a3a5EC0241e58201` | deployed 2026-11-22 with the host share ([ADR 0013](adr/0013-sale-and-settlement.md)); never minted; off the NativeMinter allow list since 2026-11-23 |
| First Treasury (no longer used) | `0xB843946A42F2791B8b932F8c0205C9D277E351B1` | deployed 2026-11-21, before the host share; off the NativeMinter allow list since 2026-11-23 |
| Treasury operator (`OPERATOR_ROLE`) | `0x528815e03Aa80b045B32840f3e26B394D0838d0d` | `fuji.env` `TREASURY_OPERATOR` |
| Treasury oracle (`ORACLE_ROLE`) | `0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50` | `fuji.env` `TREASURY_ORACLE` |
| Seed capital transaction | `0x0e58542108f3e94c92ffd93b2d0576128e75199ed4449c676ce51be4cb82e05a` | 1,000,000 COP, simulated, ref `keccak256("testnet-simulated-seed")`, in the current Treasury (the second one's was `0x802b19d9…009d`, the first one's `0x4e865bc7…424c`) |
| AccountFactory | `0x0bE806Ca77340aA50AF6586CDC2FE2561668DaEA` | [AccountFactory.sol](../chain/src/AccountFactory.sol), deployed with `zyrcle-api chain accounts-deploy`; admin is the L1 admin |
| ZyrcleAccount implementation | `0x008094fd22255b4d91846eb93042d0f05212b79f` | deployed by the factory's constructor |
| Guardian | `0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50` | the oracle key |

Advance limits are 5,000 COP per deposit and 20,000 COP per resident per UTC day
([ADR 0023](adr/0023-testnet-economics.md)).

> **The Treasury was redeployed on 2026-11-22** for the host share (ADR 0013, amendments). The new
> one does not know the advances the first one paid; the settlement worker subtracts those from what
> it sends, using the advances recorded in the `payout` table, so nobody is paid an advance twice.
>
> **It was redeployed again on 2026-11-23** for redemptions (ADR 0029). The second Treasury had
> minted nothing, so no advance carries over. Both earlier Treasuries were then taken off the
> NativeMinter allow list (`chain minter-revoke`, runbook 9.6): only the current one can mint.

### 7.5 How contracts are deployed

Deployment goes through the backend's command line, so keys stay in files on the server
([cli.py](../apps/api/src/zyrcle_api/cli.py)):

| Command | What it does |
|---|---|
| `zyrcle-api chain deploy --admin-key-file F --operator 0x.. --oracle 0x.. [--max-advance-cop 5000] [--daily-cap-cop 20000]` | Deploys the Treasury with the admin key as its admin and shares 65/15/10/10, grants the two roles, and puts the Treasury on the NativeMinter allow list. |
| `zyrcle-api chain seed --operator-key-file F --amount-cop N --ref TEXT` | Records seed capital. The reference is stored as `keccak256(TEXT)`. |
| `zyrcle-api chain state` | Prints backing, minted, available, seed capital and operations revenue, in COP. |
| `zyrcle-api chain accounts-deploy --admin-key-file F --guardian 0x..` | Deploys the AccountFactory and puts the guardian on the ContractDeployerAllowList. |
| `zyrcle-api chain accounts-guardian --admin-key-file F --guardian 0x..` | Adds the new guardian to the allow list and makes it the factory's guardian. Needs `ZYRCLE_ACCOUNT_FACTORY_ADDRESS`. |
| `zyrcle-api chain minter-revoke --admin-key-file F --address 0x..` | Takes a retired Treasury off the NativeMinter allow list, so it can no longer mint. Refuses the Treasury in `ZYRCLE_TREASURY_ADDRESS`; does nothing if the address is already off. |
| `zyrcle-api chain fund --from-key-file F --to 0x.. --amount-zyr N` | Sends native ZYR (gas) from one key to an address and prints both balances. |
| `zyrcle-api chain balance --address 0x..` | Prints an address's native ZYR. |

On the VPS these run through
[infra/l1/scripts/zyrcle-api-docker.sh](../infra/l1/scripts/zyrcle-api-docker.sh), because the host
has no `python3-venv` ([ADR 0020](adr/0020-single-vps-docker-compose.md)). The wrapper:

- runs `python:3.13-slim` with host networking, as the calling user;
- sources `infra/l1/fuji.env` and passes only `ZYRCLE_CHAIN_RPC_URL`
  (`http://127.0.0.1:9650/ext/bc/<BLOCKCHAIN_ID>/rpc`) and `ZYRCLE_TREASURY_ADDRESS` (`TREASURY`);
- mounts the repository and `~/.avalanche-cli/key` (read-only, at `/keys`);
- creates `apps/api/.venv-docker` with an editable install the first time only, then runs
  `zyrcle-api` from it.

```bash
infra/l1/scripts/zyrcle-api-docker.sh chain state
```

The wrapper does not pass `ZYRCLE_ACCOUNT_FACTORY_ADDRESS`, so `chain accounts-guardian` exits with
"set ZYRCLE_ACCOUNT_FACTORY_ADDRESS" when run through it.

The backend deploys exactly what `forge build` produces: CI fails if the exported ABI and bytecode in
`apps/api/src/zyrcle_api/contracts` differ ([ADR 0007](adr/0007-on-chain-treasury.md)).

### 7.6 Recreating the chain

[infra/l1/README.md](../infra/l1/README.md), "Runbook: recreate the chain", has ten steps: install
the pinned tools, create the P-Chain and admin keys, fund the P-Chain key, start the node, generate
the genesis, create the subnet, chain and L1 with `platform-cli`, track the L1, initialize the
validator manager with the Avalanche CLI, publish the RPC, and run the smoke test. Tool choice:
`platform-cli` 2.4.0 for P-Chain work, Avalanche CLI 1.9.7 only for genesis generation and validator
manager initialization ([ADR 0021](adr/0021-l1-operations.md)).

A new chain has new IDs. Every place that names them changes: `fuji.env`, `node.json`
(`track-subnets`), `chains/<BlockchainID>/`, `deploy/.env`, `apps/web/Dockerfile`,
`apps/mobile/src/lib/config.ts`. All contracts must be deployed again, and balances on the old
chain do not carry over.

## 8. CI/CD

### 8.1 CI ([.github/workflows/ci.yml](../.github/workflows/ci.yml))

CI runs on every push to `main` and on every pull request. A newer run on the same ref cancels the
older one. The eight jobs run in parallel:

| Job | What it checks |
|---|---|
| `packages` | `ruff` lint and format, `pytest` for `packages/protocol` and `device/simulator`. |
| `api` | `ruff`; `alembic upgrade head` on an empty database, then `alembic check` (migrations match the models); `pytest` against Postgres, Mosquitto and anvil. |
| `chain` | `forge soldeer install`, `forge fmt --check`, `forge build --sizes`, `forge test`; then `export-artifacts.py` and `git diff --exit-code` on the backend's contract artifacts and test fixtures. |
| `images` | Builds both Docker images (not pushed) and validates `deploy/compose.yml` with placeholder values. |
| `client` | Typecheck and tests of `packages/client`. |
| `mobile` | Typecheck, `expo lint`, and `expo export` for iOS and Android. |
| `web` | Typecheck, `eslint`, production build. |
| `infra` | `shellcheck` on `infra/l1/scripts/*.sh` and `deploy/*.sh`, the L1 scripts' Python unit tests, and a build of the validator image. |

### 8.2 Release ([.github/workflows/release.yml](../.github/workflows/release.yml))

- Trigger: the CI workflow completes on `main` with conclusion `success`. A manual
  `workflow_dispatch` also runs it, without the CI gate.
- It checks out the exact commit CI tested and builds with Buildx, using the GitHub Actions cache.
- It pushes `ghcr.io/diegowritescode/zyrcle-api:<sha>` (API and simulator) and
  `ghcr.io/diegowritescode/zyrcle-web:<sha>`, labelled with the source repository.
- Its step summary prints the deploy command: `deploy/deploy.sh <sha> <sha>`.
- Deploying is a separate, manual step. Nothing deploys automatically.

```mermaid
flowchart TB
  trigger["Push to main or pull request"] --> packages & apij & chainj & imagesj & clientj & mobilej & webj & infraj
  subgraph ci["CI workflow ci.yml: eight jobs in parallel"]
    packages["packages<br/>ruff, pytest: protocol, simulator"]
    apij["api<br/>ruff, alembic upgrade and check, pytest<br/>with Postgres, Mosquitto, anvil"]
    chainj["chain<br/>forge fmt, build, test<br/>ABI drift check"]
    imagesj["images<br/>docker build api and web<br/>compose config check"]
    clientj["client<br/>typecheck, tests"]
    mobilej["mobile<br/>typecheck, lint, expo export"]
    webj["web<br/>typecheck, eslint, build"]
    infraj["infra<br/>shellcheck, unittest,<br/>validator image build"]
  end
  packages & apij & chainj & imagesj & clientj & mobilej & webj & infraj --> gate{"Whole workflow succeeded<br/>on main?"}
  gate -->|"no"| stop["No images"]
  gate -->|"yes"| checkout
  dispatch["Manual workflow_dispatch<br/>skips the CI gate"] --> checkout
  subgraph rel["Release images release.yml"]
    checkout["Check out the tested SHA"] --> pushapi["Build and push zyrcle-api:SHA"] --> pushweb["Build and push zyrcle-web:SHA"] --> summary["Step summary:<br/>deploy/deploy.sh SHA SHA"]
  end
  pushapi --> ghcr[("GHCR")]
  pushweb --> ghcr
  subgraph vps["On the VPS, manual, needs Diego's approval"]
    deploy["ssh aitera-vps<br/>cd ~/apps/zyrcle, git pull<br/>deploy/deploy.sh api-sha web-sha"]
  end
  summary -.->|"copy the full SHA"| deploy
  ghcr -->|"docker compose pull"| deploy
  subgraph mob["Mobile, manual, not in CI"]
    eascmd["npx eas-cli build --profile<br/>development, preview or production"] --> easbuild["EAS cloud build<br/>@diegowritescode/zyrcle"] --> artifact["APK: development, preview<br/>app bundle: production"]
  end
```

### 8.3 Deploy procedure

`deploy/deploy.sh <api-sha> <web-sha>` is idempotent: running it twice with the same SHAs changes
nothing. Step by step ([deploy.sh](../deploy/deploy.sh)):

1. **Check the tags.** Both must be full 40-character SHAs. A SHA expanded by hand from a short one
   will not exist in GHCR.
2. **Secrets, first run only.** If `deploy/.env` is missing, create it from `.env.example` with
   `umask 077` and fresh values from Python's `secrets.token_urlsafe` (see
   [section 5.2](#52-deployenv)). Set the key paths to `$HOME/.avalanche-cli/key/zyrcle-oracle.pk`
   and `zyrcle-operator.pk`, and the UID and GID to the current user's.
3. **Update `.env`.** Rename the legacy variable names, write the two image tags, then load the file.
4. **Broker accounts.** Hash the five broker passwords with `mosquitto_passwd` in a throwaway
   `eclipse-mosquitto:2.1.4-alpine` container. Install the result as `mosquitto/passwd` and copy
   the ACL to `mosquitto/acl.runtime`, both `0600`.
5. **Images and database.** `docker compose pull --quiet` (unless `SKIP_PULL=1`), start `postgres`
   and `mosquitto`, then run `docker compose --profile ops run --rm migrate` (`alembic upgrade
   head`). The running API is not stopped first.
6. **Simulated containers.** Start `sim` and wait up to 30 s for `/keys/ctr-0004.pub.pem`. Then run
   `zyrcle-api demo seed` in a one-off `api` container with the `zyrcle_sim-keys` volume mounted
   read-only. The seed registers the demo host, sites, containers, bags and test prices, and is safe
   to repeat.
7. **Services.** `docker compose up -d --remove-orphans api web sim mosquitto postgres`, then print
   each service's status. `--remove-orphans` removes services no longer in the file; the L1 node is
   another project and is not touched.

Things `deploy.sh` does not do:

- It does not check out the given SHA. `compose.yml`, the broker files and the script come from
  whatever the checkout holds.
- It keeps no record of the previous tags; it overwrites them in `.env`.
- It does not add new variables to an existing `.env`.
- It does not back up the database before migrating.
- It does not restart Mosquitto when the broker files change.

### 8.4 Rollback

Run `deploy.sh` again with the previous SHAs. This works as long as no migration was added in
between. If one was, the older image cannot migrate the newer database, and the database must be
downgraded first. [Runbook 9.2](#92-roll-back) has the steps. Contract deployments and on-chain
state cannot be rolled back.

### 8.5 Mobile build path

Builds run on EAS in the project `@diegowritescode/zyrcle`
([ADR 0015](adr/0015-android-builds.md)). CI only typechecks, lints and
bundles the app; it never calls EAS.

| Profile ([eas.json](../apps/mobile/eas.json)) | Output | Use |
|---|---|---|
| `development` | Development client, internal distribution, APK | Replaces Expo Go for testing push. |
| `preview` | Internal distribution, APK, pointed at production | Installable test build outside the Play Store. |
| `production` | Store build, version number auto-incremented | Kept for the Play Store. It needs an `.aab`, a privacy policy and the data safety form (roadmap M7). |

- App version numbers come from EAS (`appVersionSource: remote`). The app ID is
  `xyz.deviego.zyrcle`.
- Native code is built for `armeabi-v7a` and `arm64-v8a` only. x86 emulators cannot install the
  APKs ([app.config.ts](../apps/mobile/app.config.ts)).
- The free plan has a monthly build quota and a build takes about 20 minutes, so builds are spent on
  purpose. Each one needs Diego's approval ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)).
- `eas submit` has an empty `production` entry. No store submission is recorded.
- No iOS build is recorded. iOS needs an Apple Developer account.
- First-time setup (Firebase project, `GOOGLE_SERVICES_JSON`, FCM key) is in
  [apps/mobile/README.md](../apps/mobile/README.md), "Notifications".

```bash
cd apps/mobile
npx eas-cli@latest build --profile preview --platform android
```

## 9. Runbooks

Before any of these:

- **Get Diego's approval** for deploying, deleting, contract transactions on Fuji, installing
  software on the VPS and EAS builds ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)).
- Work on the VPS as `diego`, from `~/apps/zyrcle`.
- `docker compose -f deploy/compose.yml …` reads `deploy/.env` automatically.
- Never print `deploy/.env` or a key file.
- Steps marked **Gap** have no script in the repository yet.

### 9.1 Deploy a new version

1. Check that CI and "Release images" passed for the commit. The images must exist in GHCR.
2. Deploy:
   ```bash
   ssh aitera-vps
   cd ~/apps/zyrcle && git pull
   git rev-parse HEAD                      # the full SHA of the checkout
   deploy/deploy.sh <api-sha> <web-sha>
   ```
   Keep the checkout and the images on the same commit: `deploy.sh` uses the checkout's
   `compose.yml`.
3. If `docker compose pull` hangs at "Pulling fs layer" (it happened on 2026-11-23), stop
   `deploy.sh`, pull each image with `docker pull ghcr.io/diegowritescode/zyrcle-api:<sha>` (and
   `zyrcle-web`), then run `SKIP_PULL=1 deploy/deploy.sh <api-sha> <web-sha>`. Run it with `nohup`
   and a log file so a dropped SSH session does not stop it halfway.
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

1. **Find the previous SHAs.** `deploy.sh` does not keep them. Look at `git log` on `main`, the
   "Release images" runs on GitHub, or the images still on the VPS:
   ```bash
   docker images ghcr.io/diegowritescode/zyrcle-api
   docker images ghcr.io/diegowritescode/zyrcle-web
   ```
2. **No migration in between.** Deploy the older SHAs:
   ```bash
   deploy/deploy.sh <previous-api-sha> <previous-web-sha>
   ```
   To roll back only the web app, pass the current API SHA and the previous web SHA.
3. **A migration in between.** The older image's `alembic upgrade head` fails, because the database
   is at a revision that image does not know. `deploy.sh` stops there and the newer API keeps
   running. **Gap:** this path is not scripted. Downgrade with the newer image still in `.env`, then
   deploy the older SHAs:
   ```bash
   docker compose -f deploy/compose.yml --profile ops run --rm migrate alembic downgrade <revision>
   deploy/deploy.sh <previous-api-sha> <previous-web-sha>
   ```
   Revisions are `0001` to `0013` ([apps/api/migrations/versions](../apps/api/migrations/versions)).
   A downgrade drops the tables and columns the newer migrations added, with their data. There is no
   backup to restore from.
4. Contract deployments, on-chain payments and installed mobile builds cannot be rolled back.

### 9.3 Run a migration

- **Normal path.** Every `deploy.sh` run applies `alembic upgrade head` before starting the new API.
- **On its own,** with the image named by `ZYRCLE_API_TAG` in `deploy/.env`:
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
- **Gap:** nothing backs up the database before a migration.

### 9.4 Rotate the Treasury operator or oracle key

**Gap:** most of this runbook is manual. The CLI has no command to grant or revoke Treasury roles,
to pause the Treasury, or to remove an address from an allow list.

1. **In an emergency, pause first.** The Treasury admin (L1 admin key) can call `pause()`, which
   stops advances and settlements ([ADR 0007](adr/0007-on-chain-treasury.md)). **Gap:** not scripted.
2. **Create the new key on the VPS** with the Avalanche CLI, as the L1 runbook does for its keys,
   and get its address:
   ```bash
   avalanche key create zyrcle-operator-2
   avalanche key list --fuji --keys zyrcle-operator-2 --blockchains c --pchain=false --xchain=false
   ```
   The file lands in `~/.avalanche-cli/key/`. Keep it `0600`, owned by the deploy user, and add it
   to the offline inventory ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)).
3. **Give it gas.** Send it a few ZYR from the L1 admin with `chain fund` (runbook 9.12).
4. **Move the role.** With the L1 admin key, call the Treasury's `grantRole` for the new address and
   `revokeRole` for the old one (`OPERATOR_ROLE` or `ORACLE_ROLE`). **Gap:** no command exists.
5. **Oracle only: move the guardian too.** The oracle key is also the AccountFactory guardian:
   ```bash
   infra/l1/scripts/zyrcle-api-docker.sh chain accounts-guardian \
     --admin-key-file /keys/zyrcle-l1-admin.pk --guardian <new address>
   ```
   **Gap:** the wrapper does not pass `ZYRCLE_ACCOUNT_FACTORY_ADDRESS`, so this exits until it does.
   The old key also stays on the ContractDeployerAllowList; nothing removes it.
6. **Point the API at the new file.** Change `OPERATOR_KEY_PATH` or `ORACLE_KEY_PATH` in
   `deploy/.env`, then redeploy the current version so compose recreates `api` with the new mount:
   ```bash
   grep -E '^ZYRCLE_(API|WEB)_TAG=' deploy/.env      # the current tags; prints no secret
   deploy/deploy.sh <current-api-sha> <current-web-sha>
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
| `RESEND_API_KEY`, `EXPO_ACCESS_TOKEN`, `PINATA_JWT` | Diego places these himself over SSH ([ADR 0022](adr/0022-keys-secrets-and-production-changes.md)). Revoke the old key in the provider's dashboard. |

### 9.6 Redeploy the Treasury

ADR 0013 requires this for the host share ([section 7.4](#74-contracts-on-fuji)). It is a contract
transaction on Fuji, so it needs Diego's approval.

1. **Update the code.** `git pull` on the VPS. The wrapper's editable install runs the checked-out
   code and contract artifacts. It creates `apps/api/.venv-docker` only when it is missing.
2. **Deploy.** The defaults give shares 65/15/10/10, 5,000 COP per deposit and 20,000 COP per
   resident per day:
   ```bash
   infra/l1/scripts/zyrcle-api-docker.sh chain deploy \
     --admin-key-file /keys/zyrcle-l1-admin.pk \
     --operator 0x528815e03Aa80b045B32840f3e26B394D0838d0d \
     --oracle 0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50
   ```
   It prints the new address and puts the new Treasury on the NativeMinter allow list.
3. **Record the address** as `TREASURY` in `infra/l1/fuji.env`. The wrapper reads it from there.
4. **Record the simulated seed again** ([ADR 0023](adr/0023-testnet-economics.md)):
   ```bash
   infra/l1/scripts/zyrcle-api-docker.sh chain seed \
     --operator-key-file /keys/zyrcle-operator.pk \
     --amount-cop 1000000 --ref testnet-simulated-seed
   infra/l1/scripts/zyrcle-api-docker.sh chain state
   ```
5. **Point everything at it.** `TREASURY` in `deploy/.env` and `deploy/.env.example`, the
   `VITE_TREASURY_ADDRESS` default in `apps/web/Dockerfile`, and `chain/README.md`. Commit, wait for
   the release, then run `deploy.sh`.
6. **Retire the old contract.** It stays on the NativeMinter allow list, and the oracle key keeps its
   role there, so it could still mint up to its unused backing. Take it off the allow list once the
   new one is deployed and the API points at it:
   ```bash
   infra/l1/scripts/zyrcle-api-docker.sh chain minter-revoke \
     --admin-key-file /keys/zyrcle-l1-admin.pk --address <old Treasury>
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
3. **Check the chain afterwards** with the read-only smoke test. Run it twice; the height must grow:
   ```bash
   ADMIN_ADDRESS=0xfdDD10F3BB701dCB21bF711bf3d28f96FA9a2f7d \
     infra/l1/scripts/smoke-test.sh https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc
   ```

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
     `collection-sweep`, `codes`, `notifications`, `payouts`, `settlements`, `recoveries`, `emails`.
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
   - Run the read-only smoke test twice (9.8, step 3). A height that does not grow means the chain
     is halted. An empty validator balance halts it ([ADR 0021](adr/0021-l1-operations.md)).
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
`BACKUP_DIR` and `BACKUP_KEEP_DAYS` change the folder and the retention.

To restore production from a dump, stop the API first so nothing writes meanwhile:

```bash
cd ~/apps/zyrcle/deploy
docker compose stop api
docker compose exec -T postgres psql -U zyrcle -d postgres -c "DROP DATABASE zyrcle" -c "CREATE DATABASE zyrcle OWNER zyrcle"
gunzip -c FILE | docker compose exec -T postgres psql -U zyrcle -d zyrcle -v ON_ERROR_STOP=1
docker compose start api
```

The dumps stay on the VPS: losing the machine loses them. An off-site copy is still to be decided.

### 9.11 Health and alerts

`GET /v1/operator/health` (and the console's summary) reports each outbox, devices online, the
broker, the chain's latest block and its age, the Treasury's mintable pesos and the gas of the oracle
and operator keys. Each warning is emailed to every active admin at most once a day. Thresholds are
settings (`alert_*` in [config.py](../apps/api/src/zyrcle_api/config.py)): queue stuck 30 min, any
failed row, no block for 10 min, under 100,000 COP mintable, under 1 ZYR of gas.

### 9.12 Top up gas for the backend's keys

The oracle key (advances, and as guardian it relays payments and deploys accounts) and the operator
key (sales, settlements, certificate anchors) pay gas in ZYR. The health report warns under 1 ZYR
(runbook 9.11). Send gas from the L1 admin's float:

```bash
infra/l1/scripts/zyrcle-api-docker.sh chain balance --address 0xfdDD10F3BB701dCB21bF711bf3d28f96FA9a2f7d
infra/l1/scripts/zyrcle-api-docker.sh chain fund --from-key-file /keys/zyrcle-l1-admin.pk \
  --to 0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50 --amount-zyr 20      # oracle
infra/l1/scripts/zyrcle-api-docker.sh chain fund --from-key-file /keys/zyrcle-l1-admin.pk \
  --to 0x528815e03Aa80b045B32840f3e26B394D0838d0d --amount-zyr 20      # operator
```

It is a transaction on Fuji and needs Diego's approval. The float is finite; minting more gas with
the admin key would create ZYR without backing, so it is not done.

## 10. Known gaps and risks

Each item is checked against the repository.

**Data and availability**

- **Backups stay on the VPS.** `deploy/backup.sh` runs daily from cron (runbook 9.10), but nothing copies the dumps off the machine.
- **Only the database is backed up.** Nothing backs up the `node-data` volume (the validator identity), `deploy/.env` or the key files; the L1 README asks for an offline copy of the keys, by hand.
- **A migration is not reversible by data.** `deploy.sh` migrates before starting the new API; take a backup first (runbook 9.10) so a bad migration can be undone by restoring.
- **One VPS.** It runs the application, the validator and Traefik, shared with other projects. It is
  a single point of failure for the demo and the chain ([ADR 0020](adr/0020-single-vps-docker-compose.md)).
  The memory limits add up to 4,160 MiB on a 4 GB machine ([section 4.5](#45-memory-budget)).
- **One validator.** It is a single point of failure for the chain. ADR 0002 accepts that on
  testnet; ADR 0021 asks for a second validator before any real value moves.
- **Validator fee deadline.** The balance lasts until about 2027-03-09. Topping it up is manual and
  its exact command is not recorded ([runbook 9.8](#98-top-up-the-validator)).
- **Testnet only.** ZyrcleChain runs on Fuji. ZYR has no value and the seed capital is simulated
  ([ADR 0023](adr/0023-testnet-economics.md)). The chain for real value is an open M7 decision.
- **No monitoring or alerts in the repository.** ADR 0002 mentions the VPS's existing Grafana; its
  configuration is not here. Roadmap M7 lists monitoring for the API, the broker, the validator and
  the Treasury reserve. The `/health` endpoint reports `ok` even when MQTT is down, and an unhealthy
  container is not restarted.

**Chain and keys**

- **Gas is a finite float.** The operator and oracle keys pay gas from the L1 admin's 100-ZYR
  genesis float: about 5 ZYR each on 2026-11-22 and 20 more each on 2026-11-23 (runbook 9.12),
  leaving them about 24.8 and 24.95 ZYR and the admin about 48.5. At the 2026-11-22 gas price
  (175 gwei) a payout or settlement transaction costs a few hundredths of a ZYR. Nothing refills them
  automatically; the health report warns under 1 ZYR, and the Treasury cannot mint gas for its own
  keys.
- **Hot keys on the server.** The oracle and operator keys sit on the VPS and are mounted into the
  API ([ADR 0013](adr/0013-sale-and-settlement.md)). The oracle key is also the guardian and is on
  the deployer allow list. `config.py` says production should give the guardian its own key
  (`ZYRCLE_GUARDIAN_KEY_FILE`); compose does not pass one.
- **One L1 admin key holds everything:** every precompile, the validator manager, and the admin role
  of the Treasury and the AccountFactory. It can mint directly. The repository has no procedure to
  rotate it.
- **Missing chain commands.** No command grants or revokes Treasury roles, pauses the Treasury,
  removes an allow-list entry, or tops up the validator. The wrapper does not pass the factory
  address that `chain accounts-guardian` needs.
- **RewardManager** has no reward address, although ADR 0002 says fees go to the treasury.

**Deployment**

- **Manual, unpinned deploys.** `deploy.sh` does not check out the deployed SHA, keeps no history of
  tags, and has no scripted rollback across migrations.
- **A manual release run skips CI.** `workflow_dispatch` builds and pushes images without the CI
  gate.
- **Traefik, the `edge` network, TLS certificates and DNS** are configured outside this repository.
- **Whether the GHCR images are public or private** is not recorded. If they are private, the VPS
  needs a `docker login ghcr.io`, which is not in the repository.
- **Images are pinned by tag, not digest,** except the validator's base. `postgres:17-alpine` takes
  the latest 17.x on every pull. CI's Mosquitto uses the floating `eclipse-mosquitto:2`, production
  `2.1.4-alpine`.
- **Hardening is partial.** `postgres` and `migrate` are not hardened and `migrate` has no memory
  limit, although [deploy/README.md](../deploy/README.md) says every container is.
- **The `internal` network is not isolated.** It is not marked `internal: true`, so Postgres,
  Mosquitto and the simulator can reach the internet. Any container on the `edge` network, which
  Traefik also uses, can reach the node's HTTP API on 9650.

**Devices and email**

- **The broker has no TLS and is not published.** ADR 0005 and [device-protocol.md](device-protocol.md)
  call for MQTT over TLS in production. Today only the simulator connects, inside the VPS. A
  physical container needs a published TLS listener, which is not in the repository.
- **Email is optional in compose but required in practice.** Without `RESEND_API_KEY`, operators
  cannot sign in and residents cannot recover accounts. Whether production sets it is not visible in
  the repository.

**Mobile**

- **Mobile builds are manual** and outside CI (ADR 0015). No iOS build and no store submission are
  recorded.

**Documentation drift found while writing this**

- `deploy/.env.example` says it is "Generated by bootstrap.sh"; the script is `deploy.sh`.
- `chain/README.md` shows the 65/15/10/10 shares next to a Treasury deployed with 70/15/15. It also
  mentions Hardhat contracts in `../contracts`, which ADR 0019 removed.
- `deploy/README.md` says every container is hardened; `postgres` and `migrate` are not.
