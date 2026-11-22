#!/usr/bin/env bash
# Run the backend CLI on the VPS inside python:3.13-slim (the host has no python3-venv).
# The virtualenv lives in apps/api/.venv-docker; keys are mounted read-only from ~/.avalanche-cli/key
# at /keys. Chain variables come from infra/l1/fuji.env.
#
#   infra/l1/scripts/zyrcle-api-docker.sh chain state
#   infra/l1/scripts/zyrcle-api-docker.sh chain seed --operator-key-file /keys/zyrcle-operator.pk ...
set -euo pipefail
repo="$(cd "$(dirname "$0")/../../.." && pwd)"
# shellcheck source-path=SCRIPTDIR/.. source=fuji.env
source "$repo/infra/l1/fuji.env"
rpc="http://127.0.0.1:9650/ext/bc/${BLOCKCHAIN_ID}/rpc"
run() {
  docker run -i --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e ZYRCLE_CHAIN_RPC_URL="$rpc" -e ZYRCLE_TREASURY_ADDRESS="$TREASURY" \
    -v "$repo:/repo" -v "$HOME/.avalanche-cli/key:/keys:ro" -w /repo/apps/api \
    python:3.13-slim "$@"
}
if [ ! -x "$repo/apps/api/.venv-docker/bin/zyrcle-api" ]; then
  run sh -c "python -m venv .venv-docker && .venv-docker/bin/pip install -q -e ../../packages/protocol -e ."
fi
run .venv-docker/bin/zyrcle-api "$@"
