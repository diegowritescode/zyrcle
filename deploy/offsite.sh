#!/usr/bin/env bash
# Copy backups off the VPS, encrypted (docs/adr/0034).
#
#   deploy/offsite.sh          the newest database dump; on Sundays also the keys bundle
#   deploy/offsite.sh --keys   the keys bundle now: validator identity, key files, deploy/.env
#
# Everything is encrypted with age to OFFSITE_AGE_RECIPIENT (a public key; the private key is only
# with Diego, offline) before it leaves, then streamed to an S3-compatible bucket (Cloudflare R2)
# with rclone. Both tools run in a container built from deploy/offsite/Dockerfile. This script never
# deletes anything remote: the bucket's lifecycle rule expires old copies, and its lock keeps them
# from being deleted early. Not configured: it says so and exits 0.
#
# deploy/.env: OFFSITE_AGE_RECIPIENT, OFFSITE_S3_ENDPOINT, OFFSITE_S3_BUCKET,
#              OFFSITE_S3_ACCESS_KEY_ID, OFFSITE_S3_SECRET_ACCESS_KEY
set -euo pipefail
cd "$(dirname "$0")"
backups="${BACKUP_DIR:-$HOME/backups/zyrcle}"
keys_dir="${OFFSITE_KEYS_DIR:-$HOME/.avalanche-cli/key}"
node_volume="${OFFSITE_NODE_VOLUME:-zyrcle-l1_node-data}"
image=zyrcle-offsite

set -a
# shellcheck source=/dev/null
[ -f .env ] && . ./.env
set +a
for v in OFFSITE_AGE_RECIPIENT OFFSITE_S3_ENDPOINT OFFSITE_S3_BUCKET OFFSITE_S3_ACCESS_KEY_ID OFFSITE_S3_SECRET_ACCESS_KEY; do
  if [ -z "${!v:-}" ]; then
    echo "off-site copy not configured ($v is empty in deploy/.env)"
    exit 0
  fi
done
[[ "$OFFSITE_AGE_RECIPIENT" =~ ^age1[0-9a-z]{58}$ ]] || { echo "OFFSITE_AGE_RECIPIENT is not an age public key" >&2; exit 1; }

docker image inspect "$image" >/dev/null 2>&1 || docker build -q -t "$image" offsite >/dev/null
network=()
[ -n "${OFFSITE_DOCKER_NETWORK:-}" ] && network=(--network "$OFFSITE_DOCKER_NETWORK")  # the self-test
encrypt() { docker run -i --rm "$image" age -r "$OFFSITE_AGE_RECIPIENT"; }
upload() { # remote path; the content comes on stdin
  docker run -i --rm "${network[@]}" -e HOME=/tmp \
    -e RCLONE_CONFIG_OFFSITE_TYPE=s3 -e RCLONE_CONFIG_OFFSITE_PROVIDER="${OFFSITE_S3_PROVIDER:-Cloudflare}" \
    -e RCLONE_CONFIG_OFFSITE_ENDPOINT="$OFFSITE_S3_ENDPOINT" \
    -e RCLONE_CONFIG_OFFSITE_ACCESS_KEY_ID="$OFFSITE_S3_ACCESS_KEY_ID" \
    -e RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY="$OFFSITE_S3_SECRET_ACCESS_KEY" \
    -e RCLONE_CONFIG_OFFSITE_NO_CHECK_BUCKET=true \
    "$image" rclone -q rcat --s3-no-check-bucket "offsite:$OFFSITE_S3_BUCKET/$1"
  echo "copied off site: $1"
}

if [ "${1:-}" != "--keys" ]; then
  latest=""
  for f in "$backups"/zyrcle-*.sql.gz; do
    [ -f "$f" ] || continue
    if [ -z "$latest" ] || [ "$f" -nt "$latest" ]; then latest="$f"; fi
  done
  [ -n "$latest" ] || { echo "no database dump in $backups: run backup.sh first" >&2; exit 1; }
  name="db/$(basename "$latest").age"
  encrypt < "$latest" | upload "$name"
fi

if [ "${1:-}" = "--keys" ] || [ "$(date -u +%u)" = "7" ]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  chmod 700 "$tmp"
  mkdir -p "$tmp/keys" "$tmp/node"
  cp -p "$keys_dir"/*.pk "$tmp/keys/" 2>/dev/null || true
  cp -p .env "$tmp/deploy.env" 2>/dev/null || true
  # The validator's identity (staking key, TLS certificate, BLS key), not the chain data.
  if docker volume inspect "$node_volume" >/dev/null 2>&1; then
    docker run --rm --user 0 -v "$node_volume:/data:ro" "$image" tar -c -C /data staking | tar -x -C "$tmp/node"
  fi
  tar -cz -C "$tmp" . | encrypt | upload "keys/zyrcle-keys-$(date -u +%Y%m%dT%H%M%SZ).tar.gz.age"
fi
