#!/usr/bin/env bash
# Back up the production database (docs/adr/0028): a compressed pg_dump of the zyrcle database,
# kept for BACKUP_KEEP_DAYS days (default 14) in BACKUP_DIR (default ~/backups/zyrcle).
#
#   deploy/backup.sh               dump now
#   deploy/backup.sh --check FILE  restore FILE into a throwaway Postgres and count the rows
#
# Meant for cron on the VPS, for example `15 3 * * * ~/apps/zyrcle/deploy/backup.sh`. Nothing
# leaves the machine: copying the dumps somewhere else is a separate, pending decision.
set -euo pipefail
cd "$(dirname "$0")"
dir="${BACKUP_DIR:-$HOME/backups/zyrcle}"
keep="${BACKUP_KEEP_DAYS:-14}"

check() {
  local file="$1" name="zyrcle-restore-check-$$"
  docker run -d --rm --name "$name" -e POSTGRES_PASSWORD=check -e POSTGRES_USER=zyrcle \
    -e POSTGRES_DB=zyrcle postgres:17-alpine@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73 >/dev/null
  trap 'docker rm -f "$name" >/dev/null 2>&1 || true' RETURN
  for _ in $(seq 1 30); do
    docker exec "$name" pg_isready -U zyrcle -d zyrcle >/dev/null 2>&1 && break
    sleep 1
  done
  gunzip -c "$file" | docker exec -i "$name" psql -q -U zyrcle -d zyrcle -v ON_ERROR_STOP=1 >/dev/null
  docker exec "$name" psql -U zyrcle -d zyrcle -tAc \
    "select 'revision ' || version_num from alembic_version
     union all select 'deposit_session ' || count(*) from deposit_session
     union all select 'resident ' || count(*) from resident
     union all select 'payout ' || count(*) from payout"
  echo "restore check ok: $file"
}

if [ "${1:-}" = "--check" ]; then
  check "${2:?usage: backup.sh --check FILE}"
  exit 0
fi

mkdir -p "$dir"
chmod 700 "$dir"
file="$dir/zyrcle-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose exec -T postgres pg_dump -U zyrcle -d zyrcle --no-owner | gzip -9 > "$file.partial"
mv "$file.partial" "$file"
chmod 600 "$file"
find "$dir" -name 'zyrcle-*.sql.gz' -mtime +"$keep" -delete
echo "backup: $file ($(du -h "$file" | cut -f1))"
