# ZyrcleChain v2 (infra/l1)

Own Avalanche L1 on Fuji. Native coin **ZYR, 1 ZYR = 1 COP**. Design and reasons:
[ADR 0002](../../docs/adr/0002-own-avalanche-l1.md).

| Parameter | Value |
|---|---|
| EVM chain ID | 20261121 |
| Validator management | Proof of Authority (validator manager predeployed in genesis) |
| Precompiles | NativeMinter, ContractDeployerAllowList, FeeManager, RewardManager (admin: L1 admin key); Warp |
| Genesis supply | 100 ZYR to the L1 admin, for gas ("genesis float"). Nothing else. |
| Node | `avaplatform/subnet-evm:v1.15.3` pinned by digest, P-Chain partial sync |

## Files

| Path | Purpose |
|---|---|
| `params.env` | Chain parameters and pinned versions |
| `scripts/create-config.sh` | Generates the genesis with the CLI, strips its prefunds, enables the precompiles |
| `scripts/customize_genesis.py` | The genesis transformation, with its own checks |
| `scripts/smoke-test.sh` | Verifies a running chain against the design rules without minting |
| `scripts/install-cli.sh` | Installs the pinned Avalanche CLI into `~/bin` after checking its checksum |
| `node/` | Validator container: Dockerfile, node config, compose file, chain config |
| `genesis.local.json` | Genesis used on the local test network (admin = the public ewoq test key) |

## Verified locally (2026-11-21)

- Local network (CLI 1.9.6, AvalancheGo v1.14.0): the chain boots, the PoA validator manager
  initializes, and every check in `smoke-test.sh` passes. Permission failures are the precompile
  errors (`not authorized to deploy a contract`, `non-enabled cannot mint`), not missing funds.
- Validator container against Fuji: P-Chain partial sync finished in about 10 minutes and the node
  reported healthy. Steady state: ~2.2 GB RAM, ~2% CPU, 1.5 GB of data.

## Runbook: create the chain on the VPS

Run as `diego` on the VPS from a checkout of this repo. Keys stay on the VPS and are never pasted
anywhere.

1. **Install the CLI:** `infra/l1/scripts/install-cli.sh`
2. **Create two keys**: one pays P-Chain fees, the other administers the L1.
   ```bash
   avalanche key create zyrcle-pchain
   avalanche key create zyrcle-l1-admin
   avalanche key list --fuji --keys zyrcle-pchain,zyrcle-l1-admin
   ```
   Back up `~/.avalanche-cli/key/zyrcle-*.pk` offline.
3. **Fund** the `zyrcle-pchain` P-Chain address with about 4 test AVAX: 3 go to the validator's
   continuous-fee balance (about 1.33 AVAX a month), the rest covers transaction fees.
4. **Start the node** and wait until the P-Chain reports bootstrapped:
   ```bash
   cd infra/l1/node && docker compose up -d --build
   curl -s -X POST -H 'content-type:application/json' \
     --data '{"jsonrpc":"2.0","id":1,"method":"info.isBootstrapped","params":{"chain":"P"}}' \
     127.0.0.1:9650/ext/info
   ```
5. **Generate the genesis** with the L1 admin's EVM address:
   `infra/l1/scripts/create-config.sh <zyrcle-l1-admin EVM address> fuji`
6. **Create the subnet and the chain, and convert to an L1** with this node as the only bootstrap
   validator:
   ```bash
   avalanche blockchain deploy zyrcle --fuji --key zyrcle-pchain \
     --bootstrap-endpoints http://127.0.0.1:9650 --balance 3 \
     --skip-icm-deploy --skip-relayer --convert-only
   ```
   Write down the SubnetID and BlockchainID it prints.
7. **Track the L1**: copy `node/chain-config.json` to `node/chains/<BlockchainID>/config.json`, add
   `"track-subnets": "<SubnetID>"` to `node/node.json`, then `docker compose up -d`. The chain must
   start producing blocks; a genesis problem would show up here in the node logs.
8. **Initialize the validator manager:**
   ```bash
   avalanche contract initValidatorManager zyrcle --fuji --key zyrcle-l1-admin \
     --rpc http://127.0.0.1:9650/ext/bc/<BlockchainID>/rpc
   ```
9. **Smoke test** (simulations plus one 0-ZYR self-transfer; nothing is minted):
   ```bash
   ADMIN_PRIVATE_KEY=0x$(cat ~/.avalanche-cli/key/zyrcle-l1-admin.pk) \
     infra/l1/scripts/smoke-test.sh http://127.0.0.1:9650/ext/bc/<BlockchainID>/rpc
   ```
10. **Public RPC** (optional): once `rpc.zyrcle.deviego.xyz` resolves to the VPS, start the node
    with `RPC_PUBLIC=true BLOCKCHAIN_ID=<BlockchainID>`. Traefik then exposes only
    `/ext/bc/<BlockchainID>/rpc` and `/ws`, rate limited.
11. Commit `genesis.fuji.json`, the chain config folder and the IDs.
