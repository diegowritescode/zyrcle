#!/usr/bin/env bash
# Deploy (or first-time set up) the Zyrcle stack on the VPS. Idempotent.
#
#   deploy/deploy.sh <api-image-sha> <web-image-sha>
#
# Tags must be FULL 40-character commit SHAs: images are published per commit by the release
# workflow, and a SHA expanded by hand from a short one will not exist. The images then run pinned
# by digest, the database is backed up before migrating, and every deploy is appended to
# deploy/history.log (ADR 0032).
#
#   SKIP_PULL=1            use images already on this machine (after pulling them by hand)
#   DEPLOY_ANY_CHECKOUT=1  allow a checkout other than <api-image-sha> (rolling back the web only)
set -euo pipefail
cd "$(dirname "$0")"

api_tag="${1:?usage: deploy.sh <api-sha> <web-sha>}"
web_tag="${2:?usage: deploy.sh <api-sha> <web-sha>}"
for t in "$api_tag" "$web_tag"; do
  [[ "$t" =~ ^[0-9a-f]{40}$ ]] || { echo "not a full commit SHA: $t" >&2; exit 1; }
done

# 0. compose.yml, the broker files and this script come from the checkout: it must be the commit
# whose API is deployed, or the files and the image can disagree.
head="$(git rev-parse HEAD)"
if [ "$head" != "$api_tag" ] && [ "${DEPLOY_ANY_CHECKOUT:-0}" != "1" ]; then
  echo "the checkout is at $head, not $api_tag." >&2
  echo "run: git fetch && git checkout $api_tag   (or DEPLOY_ANY_CHECKOUT=1 to roll back the web only)" >&2
  exit 1
fi
api_image="ghcr.io/diegowritescode/zyrcle-api:$api_tag"
web_image="ghcr.io/diegowritescode/zyrcle-web:$web_tag"

# A pull that hangs (it happened on 2026-11-23, "Pulling fs layer") is cut and tried again.
pull() {
  for attempt in 1 2 3; do
    timeout 300 docker pull --quiet "$1" >/dev/null && return 0
    echo "pulling $1 failed or hung (attempt $attempt of 3)" >&2
    sleep 5
  done
  return 1
}
digest_of() { # image:tag -> repository@sha256:...
  docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$1" | grep -m1 "^${1%:*}@"
}
if [ "${SKIP_PULL:-0}" != "1" ]; then
  pull "$api_image"
  pull "$web_image"
fi
api_pinned="$(digest_of "$api_image")"
web_pinned="$(digest_of "$web_image")"

secret() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }

# 1. Secrets, generated once on this machine. They never leave it.
if [ ! -f .env ]; then
  umask 077
  sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret 32)|" \
      -e "s|^JWT_SECRET=.*|JWT_SECRET=$(secret 48)|" \
      -e "s|^OPERATOR_TOKEN=.*|OPERATOR_TOKEN=$(secret 32)|" \
      -e "s|^MQTT_API_PASSWORD=.*|MQTT_API_PASSWORD=$(secret 24)|" \
      -e "s|^MQTT_CTR_0001_PASSWORD=.*|MQTT_CTR_0001_PASSWORD=$(secret 24)|" \
      -e "s|^MQTT_CTR_0002_PASSWORD=.*|MQTT_CTR_0002_PASSWORD=$(secret 24)|" \
      -e "s|^MQTT_CTR_0003_PASSWORD=.*|MQTT_CTR_0003_PASSWORD=$(secret 24)|" \
      -e "s|^MQTT_CTR_0004_PASSWORD=.*|MQTT_CTR_0004_PASSWORD=$(secret 24)|" \
      -e "s|^ORACLE_KEY_PATH=.*|ORACLE_KEY_PATH=$HOME/.avalanche-cli/key/zyrcle-oracle.pk|" \
      -e "s|^OPERATOR_KEY_PATH=.*|OPERATOR_KEY_PATH=$HOME/.avalanche-cli/key/zyrcle-operator.pk|" \
      -e "s|^DEPLOY_UID=.*|DEPLOY_UID=$(id -u)|" -e "s|^DEPLOY_GID=.*|DEPLOY_GID=$(id -g)|" \
      .env.example > .env
  echo "created deploy/.env with fresh secrets"
fi
# The web app replaced the minimal demo page (same domain): carry over an older .env.
sed -i.bak -e "s|^ZYRCLE_DEMO_TAG=|ZYRCLE_WEB_TAG=|" -e "s|^DEMO_HOST=|WEB_HOST=|" .env && rm -f .env.bak
grep -q '^ZYRCLE_API_IMAGE=' .env || echo 'ZYRCLE_API_IMAGE=' >> .env
grep -q '^ZYRCLE_WEB_IMAGE=' .env || echo 'ZYRCLE_WEB_IMAGE=' >> .env
sed -i.bak -e "s|^ZYRCLE_API_TAG=.*|ZYRCLE_API_TAG=$api_tag|" \
  -e "s|^ZYRCLE_WEB_TAG=.*|ZYRCLE_WEB_TAG=$web_tag|" \
  -e "s|^ZYRCLE_API_IMAGE=.*|ZYRCLE_API_IMAGE=$api_pinned|" \
  -e "s|^ZYRCLE_WEB_IMAGE=.*|ZYRCLE_WEB_IMAGE=$web_pinned|" .env && rm -f .env.bak
set -a
# shellcheck source=/dev/null
. ./.env
set +a

# 2. Broker accounts from the passwords in .env (hashed into mosquitto/passwd).
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
touch "$tmp/passwd"
for pair in "api:$MQTT_API_PASSWORD" "ctr-0001:$MQTT_CTR_0001_PASSWORD" "ctr-0002:$MQTT_CTR_0002_PASSWORD" \
            "ctr-0003:$MQTT_CTR_0003_PASSWORD" "ctr-0004:$MQTT_CTR_0004_PASSWORD"; do
  docker run --rm -v "$tmp:/m" "$(docker compose config --images | grep -m1 eclipse-mosquitto)" \
    mosquitto_passwd -b /m/passwd "${pair%%:*}" "${pair#*:}"
done
# Mosquitto runs as this user, so both files can be private (it warns on world-readable ones).
install -m 0600 "$tmp/passwd" mosquitto/passwd
install -m 0600 mosquitto/acl mosquitto/acl.runtime

# 3. The other images, the database, a backup, migrations.
if [ "${SKIP_PULL:-0}" != "1" ]; then
  for image in $(docker compose config --images | sort -u); do
    docker image inspect "$image" >/dev/null 2>&1 || pull "$image"
  done
fi
docker compose up -d --wait postgres mosquitto
./backup.sh  # a migration is not reversible by data: keep what was there before it
docker compose --profile ops run --rm migrate

# 4. Simulated containers (they create their keys on first start), then register them.
docker compose up -d sim
for _ in $(seq 1 30); do
  docker compose exec -T sim test -f /keys/ctr-0004.pub.pem && break
  sleep 1
done
docker compose run --rm --no-deps -v zyrcle_sim-keys:/simkeys:ro api \
  zyrcle-api demo seed --keys-dir /simkeys --devices ctr-0001,ctr-0002,ctr-0003,ctr-0004

# 5. API and web app. --remove-orphans drops services no longer in compose.yml (the old demo page).
docker compose up -d --remove-orphans api web sim mosquitto postgres
docker compose ps --format 'table {{.Service}}\t{{.Status}}'

# 6. The record: what runs now, to roll back to it or explain it later.
revision="$(docker compose --profile ops run --rm migrate alembic current 2>/dev/null | awk 'NF{l=$1} END{print l}')"
printf '%s api=%s web=%s migration=%s by=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$api_pinned" "$web_pinned" "${revision:-unknown}" "$(id -un)" >> history.log
tail -1 history.log
