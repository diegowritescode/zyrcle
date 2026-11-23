#!/usr/bin/env bash
# Stop what up.sh and apps.sh started.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE="${E2E_STATE:-$ROOT/e2e/.stack}"
for f in "$STATE"/*.pid; do
  [ -f "$f" ] || continue
  kill "$(cat "$f")" 2>/dev/null || true
  rm -f "$f"
done
