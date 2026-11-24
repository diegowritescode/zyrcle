# Deploying Zyrcle

The production stack on the VPS: Postgres, Mosquitto, the API (with its background workers), the
container simulator and the web app, behind the existing Traefik. The L1 node runs separately
(`infra/l1/node`); the API reaches it on the `edge` network.

| Service | Exposed as | Notes |
|---|---|---|
| `api` | `https://zyrcle-backend.deviego.xyz` | rate limited; reads the oracle, operator and guardian keys from the host (`ORACLE_KEY_PATH`, `OPERATOR_KEY_PATH`, `GUARDIAN_KEY_PATH`) |
| `web` | `https://zyrcle.deviego.xyz` | the web app (`apps/web`): static files, unprivileged nginx, strict CSP |
| `postgres`, `mosquitto`, `sim` | internal network only | never published |

`mosquitto`, `api`, `sim` and `web` are read-only, without Linux capabilities, with
`no-new-privileges`. Every long-running container has a memory limit. `postgres` and the one-off
`migrate` are not hardened, and `migrate` has no memory limit. Every image runs pinned by digest.

## Release

Every commit on `main` that passes CI gets two images, tagged with the **full** commit SHA:
`ghcr.io/diegowritescode/zyrcle-api:<sha>` and `ghcr.io/diegowritescode/zyrcle-web:<sha>`
(`.github/workflows/release.yml`). A manual run of the workflow publishes only a commit whose CI
passed. The workflow summary prints both images by digest and the deploy command. Take the SHA from
that summary or `git rev-parse HEAD`, never by expanding a short SHA by hand.

## Deploy

```bash
ssh aitera-vps
cd ~/apps/zyrcle && git fetch && git checkout <sha>
deploy/deploy.sh <sha> <sha>       # API image, web image
git checkout main                  # so the next git pull works
```

`deploy.sh` is idempotent ([ADR 0032](../docs/adr/0032-deploys-pinned-recorded-and-backed-up.md)).
It stops unless the checkout is the API's commit, because `compose.yml`, the broker files and the
script come from the checkout (`DEPLOY_ANY_CHECKOUT=1` allows another one, to roll back only the
web app). Then it:

1. pulls both images, each pull cut after 5 minutes and tried three times (`SKIP_PULL=1` uses images
   already on the machine), and reads their digests;
2. the first time only, generates `deploy/.env` with fresh secrets (database password, JWT secret,
   operator token, broker passwords), created on the server and never leaving it;
3. writes the tags and the images pinned by digest (`ZYRCLE_API_IMAGE`, `ZYRCLE_WEB_IMAGE`) into
   `.env`, and adds `GUARDIAN_KEY_PATH`, pointing at the oracle key, if it is missing;
4. hashes the broker passwords;
5. starts Postgres and Mosquitto, backs up the database with `backup.sh`, and applies migrations;
6. starts the simulated containers and registers them (`zyrcle-api demo seed`);
7. starts the API and the web app (`--remove-orphans`; the L1 node is a separate compose project
   and is not touched);
8. appends a line to `deploy/history.log` (not in git): time, both images by digest, migration
   revision, user.

An older `.env` from the demo-page days (`ZYRCLE_DEMO_TAG`, `DEMO_HOST`) is renamed in place. Other
variables added to `.env.example` later are not copied into an existing `.env`; add them by hand.

The shared operator token for `/v1/operator/*` is `OPERATOR_TOKEN` in `deploy/.env`. It is for
machines (seed, scripts); people sign in to `/console` with their own operator account
([ADR 0014](../docs/adr/0014-operator-accounts.md)). Full operation guide, rollback included:
[docs/infrastructure.md](../docs/infrastructure.md), sections 8.3 and 9.

## Checks

```bash
docker compose -f deploy/compose.yml ps
tail -1 deploy/history.log
curl -s https://zyrcle-backend.deviego.xyz/health          # {"ok":true,"mqtt":true}
curl -s https://zyrcle-backend.deviego.xyz/v1/stats
curl -s https://zyrcle-backend.deviego.xyz/v1/demo/containers
curl -sI https://zyrcle.deviego.xyz | grep -i content-security-policy
```

## Backups

`deploy/backup.sh` dumps the database to `~/backups/zyrcle` (14 days) and `deploy/backup.sh --check
FILE` proves a dump restores. It runs daily from cron at 03:15 UTC, and before every migration.
`deploy/offsite.sh` sends the newest dump, and on Sundays the keys bundle, encrypted with `age` to a
bucket ([ADR 0034](../docs/adr/0034-encrypted-off-site-backups.md)); it does nothing until its
`OFFSITE_*` settings are in `deploy/.env`. CI proves it with `deploy/offsite-selftest.sh`. See
[docs/infrastructure.md](../docs/infrastructure.md), runbook 9.10, and
[ADR 0028](../docs/adr/0028-pilot-readiness.md).
