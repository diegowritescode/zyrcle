# ADR 0032: Deploys pinned by digest, recorded, and backed up before migrating

- Status: proposed (2026-11-23)
- Decided by: Claude, building block 3 (M9) under ADR 0030, which Diego confirmed. Not yet
  confirmed.

## Context
`deploy.sh` (ADR 0020) ran images by tag, took `compose.yml` from whatever the checkout held, kept no
record of what it deployed, migrated without a backup, and pulled with no time limit: on 2026-11-23
a pull hung for more than ten minutes at "Pulling fs layer". The release workflow could also be run
by hand for a commit whose CI had not passed. Postgres, Mosquitto and the base images floated on
their tags.

## Decision
- **Images run by digest.** `deploy.sh` pulls the two images by their commit tag, reads their
  digests, and writes `ZYRCLE_API_IMAGE` and `ZYRCLE_WEB_IMAGE` (`repository@sha256:…`) into
  `deploy/.env`; compose runs those. The release prints both digests in its summary.
- **The checkout must be the deployed commit.** `deploy.sh` stops unless `git rev-parse HEAD` is the
  API's commit, because `compose.yml`, the broker files and the script come from the checkout.
  `DEPLOY_ANY_CHECKOUT=1` allows another checkout, for rolling back only the web app.
- **Pulls are cut after 5 minutes and tried three times.**
- **Backup before migrating.** `deploy.sh` runs `backup.sh` after Postgres is up and before
  `alembic upgrade head`.
- **Every deploy is recorded** in `deploy/history.log` on the VPS (not in git): time, both images by
  digest, migration revision, user. Rollbacks start from it.
- **A manual release needs a passed CI.** On `workflow_dispatch` the release checks that CI succeeded
  for the commit and stops otherwise.
- **Base images pinned by digest** (Python, Node, nginx, Postgres, Mosquitto; the validator's already
  was), with Dependabot opening weekly pull requests for Docker and compose images and monthly ones
  for GitHub Actions. Those pull requests run the whole CI, end-to-end journeys included.

## Consequences
- What runs in production can be named exactly and rebuilt from the history file.
- Rolling back the API means checking out the older commit first, then `git checkout main` again
  for the next `git pull`.
- A rollback across a migration is still manual: downgrade first, then deploy (runbook 9.2).
- Updating Postgres or Mosquitto now happens through a reviewed pull request, not on a pull.
