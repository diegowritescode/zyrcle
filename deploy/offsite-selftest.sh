#!/usr/bin/env bash
# Prove offsite.sh end to end without a real bucket (docs/adr/0034): an S3 stand-in (rclone serve
# s3), a throwaway age key, a fake dump, key file and validator identity. Uploads both copies,
# downloads them, decrypts them with the private key, and checks they are what went in. Run in CI.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
image=zyrcle-offsite
net=zyrcle-offsite-test
volume=zyrcle-offsite-test-node
work="$(mktemp -d)"
cleanup() {
  docker rm -f zyrcle-offsite-s3 >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

docker build -q -t "$image" "$here/offsite" >/dev/null
docker network create "$net" >/dev/null
docker run -d --rm --name zyrcle-offsite-s3 --network "$net" --user 0 "$image" sh -c \
  'mkdir -p /data/zyrcle-backups && rclone serve s3 --auth-key test,testsecret --addr :8080 /data' >/dev/null

# What a VPS would hold.
mkdir -p "$work/backups" "$work/keys"
head -c 4096 /dev/urandom | gzip > "$work/backups/zyrcle-20261123T031500Z.sql.gz"
echo "0xdeadbeef" > "$work/keys/zyrcle-test.pk"
docker volume create "$volume" >/dev/null
docker run --rm --user 0 -v "$volume:/data" "$image" sh -c \
  'mkdir -p /data/staking /data/db && echo key > /data/staking/staker.key && echo big > /data/db/chain'

# A throwaway age key: the private half stays in $work, like Diego's stays offline.
docker run --rm "$image" age-keygen 2>/dev/null > "$work/age.key"
recipient="$(docker run -i --rm "$image" age-keygen -y < "$work/age.key")"

run_offsite() {
  BACKUP_DIR="$work/backups" OFFSITE_KEYS_DIR="$work/keys" OFFSITE_NODE_VOLUME="$volume" \
  OFFSITE_AGE_RECIPIENT="$recipient" OFFSITE_S3_ENDPOINT=http://zyrcle-offsite-s3:8080 \
  OFFSITE_S3_BUCKET=zyrcle-backups OFFSITE_S3_ACCESS_KEY_ID=test OFFSITE_S3_SECRET_ACCESS_KEY=testsecret \
  OFFSITE_S3_PROVIDER=Other OFFSITE_DOCKER_NETWORK="$net" "$here/offsite.sh" "$@"
}
for _ in $(seq 1 20); do docker logs zyrcle-offsite-s3 2>&1 | grep -q "Starting s3 server" && break; sleep 0.5; done
run_offsite
run_offsite --keys

fetch() { # remote path -> stdout, decrypted
  docker run --rm --network "$net" -e HOME=/tmp \
    -e RCLONE_CONFIG_T_TYPE=s3 -e RCLONE_CONFIG_T_PROVIDER=Other \
    -e RCLONE_CONFIG_T_ENDPOINT=http://zyrcle-offsite-s3:8080 \
    -e RCLONE_CONFIG_T_ACCESS_KEY_ID=test -e RCLONE_CONFIG_T_SECRET_ACCESS_KEY=testsecret \
    "$image" rclone -q cat "t:zyrcle-backups/$1" \
  | docker run -i --rm -v "$work/age.key:/key:ro" "$image" age -d -i /key
}
listing="$(docker run --rm --network "$net" -e HOME=/tmp -e RCLONE_CONFIG_T_TYPE=s3 \
  -e RCLONE_CONFIG_T_PROVIDER=Other -e RCLONE_CONFIG_T_ENDPOINT=http://zyrcle-offsite-s3:8080 \
  -e RCLONE_CONFIG_T_ACCESS_KEY_ID=test -e RCLONE_CONFIG_T_SECRET_ACCESS_KEY=testsecret \
  "$image" rclone -q lsf -R t:zyrcle-backups)"
echo "$listing"
fetch db/zyrcle-20261123T031500Z.sql.gz.age | cmp - "$work/backups/zyrcle-20261123T031500Z.sql.gz"
bundle="$(echo "$listing" | grep '^keys/zyrcle-keys-' | head -1)"
contents="$(fetch "$bundle" | tar -tz)"
for want in ./keys/zyrcle-test.pk ./node/staking/staker.key; do
  echo "$contents" | grep -qx "$want" || { echo "missing from the keys bundle: $want" >&2; exit 1; }
done
if echo "$contents" | grep -q "db/chain"; then echo "the chain data must not be in the bundle" >&2; exit 1; fi
echo "off-site copy ok: uploaded, encrypted, and restored with the private key"
