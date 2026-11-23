#!/usr/bin/env bash
# The whole Zyrcle system on one machine, from this checkout, for the end-to-end tests (ADR 0031).
#
#   anvil (ZyrcleChain stand-in) 8546 · simulator control 8091 · API 8010
#   web 4180 · mobile web 8092 · Pinata, IPFS gateway and Anthropic stand-ins 8093 (apps.sh: the apps)
#
# Needs Postgres at E2E_PG, Mosquitto on localhost:1883 with the development passwords
# (apps/api/dev/mosquitto), anvil (Foundry), node, and a Python with the API installed (E2E_PY, the
# folder of its executables). A fresh database, chain and simulator every run. State and logs go to
# E2E_STATE (default e2e/.stack). Stop everything with down.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STACK="$ROOT/e2e/stack"
STATE="${E2E_STATE:-$ROOT/e2e/.stack}"
PY="${E2E_PY:-$ROOT/apps/api/.venv/bin}"
PG="${E2E_PG:-postgresql://zyrcle:zyrcle@localhost:5432}"
DB=zyrcle_e2e
API_DIR="$ROOT/apps/api"
DEVICES=ctr-0001,ctr-0002,ctr-0003,ctr-0004

"$STACK/down.sh" >/dev/null 2>&1 || true
rm -rf "$STATE"
mkdir -p "$STATE/keys" "$STATE/sim-state"
cd "$STATE"

wait_for() { # url, what
  for _ in $(seq 1 120); do curl -sf -o /dev/null "$1" && return 0; sleep 0.5; done
  echo "timed out waiting for $2 ($1)" >&2
  return 1
}

(exec anvil --port 8546 --chain-id 20261121 --silent) > anvil.log 2>&1 &
echo $! > anvil.pid
(exec node "$STACK/fake-services.mjs" 8093) > services.log 2>&1 &
echo $! > services.pid

"$PY/python" - "$PG" "$DB" <<'PY'
import asyncio, sys
import asyncpg

async def main(url: str, db: str) -> None:
    conn = await asyncpg.connect(url + "/postgres")
    await conn.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
    await conn.execute(f'CREATE DATABASE "{db}"')
    await conn.close()

asyncio.run(main(*sys.argv[1:]))
PY

for _ in $(seq 1 60); do
  curl -sf -o /dev/null -X POST -H 'content-type: application/json' \
    --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' http://127.0.0.1:8546 && break
  sleep 0.5
done
(cd "$API_DIR" && ANVIL_RPC=http://127.0.0.1:8546 "$PY/python" dev/local_chain.py) > chain.env

cat > api.env <<ENV
ZYRCLE_DATABASE_URL=${PG/postgresql:/postgresql+asyncpg:}/$DB
ZYRCLE_MQTT_PASSWORD=dev-password
ZYRCLE_JWT_SECRET=e2e-secret-$(openssl rand -hex 16)
ZYRCLE_OPERATOR_TOKEN=e2e-operator-token-$(openssl rand -hex 16)
ZYRCLE_SIWE_DOMAIN=localhost
ZYRCLE_CORS_ORIGINS=http://localhost:4180,http://localhost:8092
ZYRCLE_DEMO_SIMULATOR_URL=http://127.0.0.1:8091
ZYRCLE_PAYOUT_INTERVAL_S=1
ZYRCLE_SETTLEMENT_INTERVAL_S=1
ZYRCLE_RELAY_INTERVAL_S=1
ZYRCLE_COLLECTION_IDLE_TIMEOUT_S=900
ZYRCLE_IDLE_TIMEOUT_S=300
ZYRCLE_PINATA_API_URL=http://127.0.0.1:8093
ZYRCLE_PINATA_JWT=e2e-pinata-jwt
ZYRCLE_IPFS_GATEWAY=http://127.0.0.1:8093/ipfs/
ZYRCLE_ANTHROPIC_API_KEY=e2e-anthropic-key
ZYRCLE_ANTHROPIC_BASE_URL=http://127.0.0.1:8093
ENV
cat chain.env >> api.env
set -a
# shellcheck source=/dev/null
. ./api.env
set +a

(cd "$API_DIR" && "$PY/alembic" upgrade head) > migrate.log 2>&1
(ZYRCLE_SIM_PASSWORD=dev-password exec "$PY/zyrcle-sim" serve --broker localhost \
  --keys-dir "$STATE/keys" --state-dir "$STATE/sim-state" --devices "$DEVICES" \
  --control-port 8091) > sim.log 2>&1 &
echo $! > sim.pid
for _ in $(seq 1 60); do [ -f keys/ctr-0004.pub.pem ] && break; sleep 0.5; done
(cd "$API_DIR" && "$PY/zyrcle-api" demo seed --keys-dir "$STATE/keys" --devices "$DEVICES") \
  > seed.log 2>&1 || { cat seed.log >&2; exit 1; }
(cd "$API_DIR" && exec "$PY/uvicorn" zyrcle_api.main:create_app --factory --port 8010) \
  > api.log 2>&1 &
echo $! > api.pid
wait_for http://127.0.0.1:8010/health "the API"
echo "stack up: API http://127.0.0.1:8010, state in $STATE"
