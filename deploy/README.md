# Deploying Zyrcle

The production stack on the VPS: Postgres, Mosquitto, the API (with the payout worker), the
container simulator and the demo page, behind the existing Traefik. The L1 node runs separately
(`infra/l1/node`); the API reaches it on the `edge` network.

| Service | Exposed as | Notes |
|---|---|---|
| `api` | `https://zyrcle-backend.deviego.xyz` | rate limited; reads the oracle key from the host |
| `demo` | `https://zyrcle.deviego.xyz` | static page, unprivileged nginx |
| `postgres`, `mosquitto`, `sim` | internal network only | never published |

Every container is read-only, without Linux capabilities, with `no-new-privileges` and a memory
limit.

## Release

Every commit on `main` that passes CI gets two images, tagged with the **full** commit SHA:
`ghcr.io/diegowritescode/zyrcle-api:<sha>` and `ghcr.io/diegowritescode/zyrcle-demo:<sha>`
(`.github/workflows/release.yml`). Take the SHA from the workflow summary or `git rev-parse HEAD`,
never by expanding a short SHA by hand.

## Deploy

```bash
ssh aitera-vps
cd ~/apps/zyrcle && git pull
deploy/deploy.sh <api-sha> <demo-sha>
```

`deploy.sh` is idempotent. The first time it generates `deploy/.env` with fresh secrets (database
password, JWT secret, operator token, broker passwords); they are created on the server and never
leave it. Every run hashes the broker passwords, pulls the images, applies migrations, starts the
simulated containers, registers them (`zyrcle-api demo seed`) and starts the API and the page.

The operator token for `/v1/operator/*` is `OPERATOR_TOKEN` in `deploy/.env`.

## Checks

```bash
docker compose -f deploy/compose.yml ps
curl -s https://zyrcle-backend.deviego.xyz/health          # {"ok":true,"mqtt":true}
curl -s https://zyrcle-backend.deviego.xyz/v1/demo/containers
```
