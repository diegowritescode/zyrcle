#!/usr/bin/env bash
# Build the web app and the mobile app (exported for the web) against the stack of up.sh, and serve
# them on 4180 and 8092 with a fallback to index.html. Run after up.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE="${E2E_STATE:-$ROOT/e2e/.stack}"
set -a
. "$STATE/chain.env"
set +a

(cd "$ROOT/apps/web" && VITE_API_URL=http://localhost:8010 VITE_RPC_URL=http://127.0.0.1:8546 \
  VITE_SIWE_DOMAIN=localhost VITE_TREASURY_ADDRESS="$ZYRCLE_TREASURY_ADDRESS" \
  VITE_IPFS_GATEWAY=http://127.0.0.1:8093/ipfs/ \
  npx vite build --outDir "$STATE/web-dist" --emptyOutDir) > "$STATE/web-build.log" 2>&1
(cd "$ROOT/apps/mobile" && EXPO_PUBLIC_API_URL=http://localhost:8010 \
  EXPO_PUBLIC_RPC_URL=http://127.0.0.1:8546 EXPO_PUBLIC_SIWE_DOMAIN=localhost \
  EXPO_PUBLIC_ACCOUNT_FACTORY="$ZYRCLE_ACCOUNT_FACTORY_ADDRESS" \
  EXPO_PUBLIC_WEB_URL=http://localhost:4180 \
  npx expo export -p web --output-dir "$STATE/mobile-dist") > "$STATE/mobile-build.log" 2>&1

(exec node "$ROOT/e2e/stack/static.mjs" "$STATE/web-dist" 4180) > "$STATE/web.log" 2>&1 &
echo $! > "$STATE/web.pid"
(exec node "$ROOT/e2e/stack/static.mjs" "$STATE/mobile-dist" 8092) > "$STATE/mobile.log" 2>&1 &
echo $! > "$STATE/mobile.pid"
for port in 4180 8092; do
  for _ in $(seq 1 40); do curl -sf -o /dev/null "http://localhost:$port/" && break; sleep 0.25; done
done
echo "apps up: web http://localhost:4180, mobile http://localhost:8092"
