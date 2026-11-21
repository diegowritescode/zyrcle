#!/usr/bin/env bash
# Create the ZyrcleChain configuration in the local Avalanche CLI and write the final genesis
# into infra/l1/genesis.<label>.json.
#
# Usage: create-config.sh <admin-evm-address> <label> [cli-chain-name]
#   admin-evm-address  owns the validator manager, the proxy admin and every precompile
#   label              suffix for the genesis file, e.g. "fuji" or "local"
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source-path=SCRIPTDIR/.. source=params.env
source "$here/params.env"

admin="${1:?admin EVM address required}"
label="${2:?label required (fuji|local)}"
name="${3:-$CHAIN_NAME}"
cli_genesis="$HOME/.avalanche-cli/subnets/$name/genesis.json"
out="$here/genesis.$label.json"

common=(--evm --proof-of-authority
  --validator-manager-owner "$admin" --proxy-contract-owner "$admin"
  --evm-chain-id "$EVM_CHAIN_ID" --evm-token "$TOKEN_SYMBOL"
  --vm-version "$SUBNET_EVM_VERSION" --warp --icm=false
  --force --skip-update-check)

# 1. Let the CLI generate the base genesis (validator manager predeploys owned by the admin).
avalanche blockchain create "$name" "${common[@]}" --production-defaults </dev/null >/dev/null

# 2. Strip the CLI prefunds and enable the precompiles.
python3 "$here/scripts/customize_genesis.py" "$cli_genesis" "$admin" "$ADMIN_GAS_FLOAT_ZYR" "$out"

# 3. Recreate the CLI configuration from the customized genesis. With --genesis the CLI rejects
#    --evm-chain-id and --warp (they come from the file) and would prompt for the rest.
avalanche blockchain create "$name" --evm --genesis "$out" --evm-token "$TOKEN_SYMBOL" --icm=false \
  --proof-of-authority --validator-manager-owner "$admin" --proxy-contract-owner "$admin" \
  --vm-version "$SUBNET_EVM_VERSION" --force --skip-update-check </dev/null >/dev/null
cmp -s <(python3 -m json.tool --sort-keys "$out") <(python3 -m json.tool --sort-keys "$cli_genesis") \
  || { echo "CLI genesis differs from $out" >&2; exit 1; }
echo "CLI configuration '$name' now uses $out"
