#!/usr/bin/env bash
# Check a running ZyrcleChain against its design rules (docs/adr/0002-own-avalanche-l1.md).
#
# Usage: ADMIN_PRIVATE_KEY=0x... smoke-test.sh <rpc-url>   full mode
#        ADMIN_ADDRESS=0x...     smoke-test.sh <rpc-url>   read-only mode, no key needed
# The admin key never goes on the command line, so it stays out of shell history.
# Needs Foundry's `cast`. Permission checks run as eth_call simulations, so nothing is minted and
# no contract is deployed. The only transaction is a 0-ZYR self-transfer from the admin to prove
# blocks are produced. Set SMOKE_MINT=1 (local networks only) to also mint 1 ZYR for real.
set -euo pipefail

rpc="${1:?rpc url required}"
: "${ADMIN_PRIVATE_KEY:=}"
[ -n "$ADMIN_PRIVATE_KEY" ] || [ -n "${ADMIN_ADDRESS:-}" ] || { echo "set ADMIN_PRIVATE_KEY or ADMIN_ADDRESS" >&2; exit 2; }
here="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source-path=SCRIPTDIR/.. source=params.env
source "$here/params.env"

DEPLOYER_ALLOWLIST=0x0200000000000000000000000000000000000000
NATIVE_MINTER=0x0200000000000000000000000000000000000001
FEE_MANAGER=0x0200000000000000000000000000000000000003
REWARD_MANAGER=0x0200000000000000000000000000000000000004
WARP=0x0200000000000000000000000000000000000005
ADMIN_ROLE=2

pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; exit 1; }
# expect <description> <command...>: the command must succeed. refuse: it must fail.
expect() { local d=$1; shift; if "$@"; then pass "$d"; else fail "$d"; fi; }
refuse() { local d=$1; shift; if "$@"; then fail "$d"; else pass "$d"; fi; }

if [ -n "$ADMIN_PRIVATE_KEY" ]; then
  admin=$(cast wallet address --private-key "$ADMIN_PRIVATE_KEY")
else
  admin="$ADMIN_ADDRESS"
fi
outsider_key=$(cast wallet new --json | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["private_key"])')
outsider=$(cast wallet address --private-key "$outsider_key")
echo "admin    $admin"
echo "outsider $outsider (fresh key)"

expect "chain id is $EVM_CHAIN_ID" [ "$(cast chain-id --rpc-url "$rpc")" = "$EVM_CHAIN_ID" ]

for pc in "$DEPLOYER_ALLOWLIST:deployer allow list" "$NATIVE_MINTER:native minter" \
          "$FEE_MANAGER:fee manager" "$REWARD_MANAGER:reward manager"; do
  role=$(cast call --rpc-url "$rpc" "${pc%%:*}" "readAllowList(address)(uint256)" "$admin")
  expect "admin is admin of ${pc#*:} (role $role)" [ "$role" = "$ADMIN_ROLE" ]
done

warp_id=$(cast call --rpc-url "$rpc" "$WARP" "getBlockchainID()(bytes32)")
expect "warp precompile answers (blockchain id $warp_id)" \
  [ "$warp_id" != "0x0000000000000000000000000000000000000000000000000000000000000000" ]

# Permissions, simulated with eth_call (no state change, no balance needed).
allowed() { cast call -q --rpc-url "$rpc" --from "$1" "${@:2}" >/dev/null 2>&1; }
expect "admin can mint" \
  allowed "$admin" "$NATIVE_MINTER" "mintNativeCoin(address,uint256)" "$outsider" 1ether
refuse "outsider cannot mint" \
  allowed "$outsider" "$NATIVE_MINTER" "mintNativeCoin(address,uint256)" "$outsider" 1ether

# Init code that deploys a one-byte contract.
initcode=0x600160008160ff8253f3
expect "admin can deploy contracts" allowed "$admin" --create "$initcode"
refuse "outsider cannot deploy contracts" allowed "$outsider" --create "$initcode"

if [ -n "$ADMIN_PRIVATE_KEY" ]; then
  # One real transaction proves the chain produces blocks.
  before=$(cast block-number --rpc-url "$rpc")
  cast send -q --rpc-url "$rpc" --private-key "$ADMIN_PRIVATE_KEY" "$admin" --value 0
  after=$(cast block-number --rpc-url "$rpc")
  expect "blocks are produced (height $before -> $after)" [ "$after" -gt "$before" ]
else
  height=$(cast block-number --rpc-url "$rpc")
  expect "chain has produced blocks (height $height)" [ "$height" -gt 0 ]
fi

if [ "${SMOKE_MINT:-0}" = "1" ]; then
  cast send -q --rpc-url "$rpc" --private-key "$ADMIN_PRIVATE_KEY" "$NATIVE_MINTER" \
    "mintNativeCoin(address,uint256)" "$outsider" 1ether
  expect "real mint of 1 ZYR landed" \
    [ "$(cast balance --rpc-url "$rpc" "$outsider")" = "1000000000000000000" ]
fi

# What a plain transfer costs, in pesos.
gas_price=$(cast gas-price --rpc-url "$rpc")
python3 -c "p=$gas_price; print(f'  info transfer cost: {21000*p/1e18:.6f} COP at {p/1e9:g} gwei')"
echo "all checks passed"
