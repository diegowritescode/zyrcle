# ZyrcleChain v2 (infra/l1)

Own Avalanche L1 on Fuji. Native coin **ZYR, 1 ZYR = 1 COP**. Design and reasons:
[ADR 0002](../../docs/adr/0002-own-avalanche-l1.md).

| Parameter | Value |
|---|---|
| EVM chain ID | 20261121 |
| Validator management | Proof of Authority (validator manager predeployed in genesis) |
| Precompiles | NativeMinter, ContractDeployerAllowList, FeeManager, RewardManager (admin: L1 admin key); Warp |
| Genesis supply | 100 ZYR to the L1 admin, for gas ("genesis float"). Nothing else. |
| Node | `avaplatform/subnet-evm:v1.15.3` pinned by digest, P-Chain partial sync, standard Subnet-EVM VM ID |

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

## ZyrcleChain v2 on Fuji (live since 2026-11-22)

| | |
|---|---|
| Public RPC | `https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc` |
| EVM chain ID | 20261121 |
| Subnet ID | `YZ1nRuEqM6LGAJoQqEkyirLvQbfxps8LutUBKFPGaYRjYSjMN` |
| Blockchain ID | `hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8` |
| Validator manager (PoA) | `0x0Feedc0de0000000000000000000000000000000` |
| Validator | `NodeID-LEXURXpvabdwVCyUZeTUKLFPf2won5DXp`, weight 100, 4.7 AVAX fee balance |
| L1 admin (precompiles, validator manager owner) | `0xfdDD10F3BB701dCB21bF711bf3d28f96FA9a2f7d` |

All IDs are also in `fuji.env`. The read-only smoke test passes against the public RPC:

```bash
ADMIN_ADDRESS=0xfdDD10F3BB701dCB21bF711bf3d28f96FA9a2f7d \
  infra/l1/scripts/smoke-test.sh https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc
```

Only `/ext/bc/<BlockchainID>/rpc` and `/ws` are public; the node's info, admin and P-Chain APIs
return 404 from outside.

## Tooling gaps found on 2026-11-22

AvalancheGo v1.15 removed `platform.getBalance` and `avax.getAtomicTxStatus`. Avalanche CLI 1.9.7
(maintenance mode since December 2025) still calls both, so on Fuji it can neither deploy an L1 nor
finish a C-Chain to P-Chain transfer. What works:

| Step | Tool |
|---|---|
| Subnet, chain, conversion to L1, validator balance | `platform-cli` 2.4.0 (maintained by Ava Labs) |
| Genesis generation, validator manager initialization | Avalanche CLI 1.9.7 (no removed APIs on these paths) |
| P-Chain address of a CLI key | `scripts/pchain_address.py` |
| Finishing a stuck C-Chain to P-Chain transfer | `tools/import-atomic.mjs` |

## Runbook: recreate the chain

Run as `diego` on the VPS from `~/apps/zyrcle`. Keys stay on the VPS; commands read them from the key
files through `AVALANCHE_PRIVATE_KEY`, so they never appear in process arguments.

1. **Install the tools** into `~/bin`, checksums verified:
   `infra/l1/scripts/install-cli.sh`, plus the `platform-cli` release tarball (its binary is named
   `platform`; install it as `~/bin/platform-cli`).
2. **Create two keys:** `avalanche key create zyrcle-pchain` and `avalanche key create zyrcle-l1-admin`.
   Get the admin's EVM address with
   `avalanche key list --fuji --keys zyrcle-l1-admin --blockchains c --pchain=false --xchain=false`
   and the P-Chain address with `infra/l1/scripts/pchain_address.py ~/.avalanche-cli/key/zyrcle-pchain.pk`.
   Back up `~/.avalanche-cli/key/zyrcle-*.pk` offline.
3. **Fund** the `zyrcle-pchain` key with about 5 test AVAX on the P-Chain. Funds sent to its C-Chain
   address can be moved with `avalanche key transfer --c-chain-sender --p-chain-receiver` followed by
   `tools/import-atomic.mjs`.
4. **Start the node** (`cd infra/l1/node && docker compose up -d --build`) and wait for
   `info.isBootstrapped` on the P-Chain (about 12 minutes on the VPS).
5. **Generate the genesis:** `infra/l1/scripts/create-config.sh <admin EVM address> fuji`.
6. **Create the subnet, the chain and the L1** (`export AVALANCHE_PRIVATE_KEY=0x$(cat ~/.avalanche-cli/key/zyrcle-pchain.pk)` first):
   ```bash
   platform-cli subnet create --network fuji
   platform-cli chain create --network fuji --subnet-id <SubnetID> \
     --genesis infra/l1/genesis.fuji.json --name zyrcle
   platform-cli subnet convert-to-l1 --network fuji --subnet-id <SubnetID> \
     --chain-id <BlockchainID> --manager 0x0Feedc0de0000000000000000000000000000000 \
     --validators http://127.0.0.1:9650 --validator-balance 4.7
   ```
7. **Track the L1:** add `"track-subnets": "<SubnetID>"` to `node/node.json`, copy
   `node/chain-config.json` to `node/chains/<BlockchainID>/config.json`, then
   `docker compose up -d --force-recreate`.
8. **Initialize the validator manager.** The CLI needs the deployment in its sidecar
   (`~/.avalanche-cli/subnets/zyrcle/sidecar.json` → `Networks.Fuji`: subnet and blockchain IDs, RPC
   endpoint, validator manager address and the bootstrap validator's NodeID, BLS key, PoP and
   validation ID). Then:
   ```bash
   avalanche contract initValidatorManager zyrcle --fuji --key zyrcle-l1-admin \
     --rpc http://127.0.0.1:9650/ext/bc/<BlockchainID>/rpc
   ```
9. **Public RPC:** write `node/.env` with `RPC_PUBLIC=true`, `RPC_HOST=rpc.zyrcle.deviego.xyz` and
   `BLOCKCHAIN_ID=<BlockchainID>`, then `docker compose up -d`.
10. **Smoke test** with the read-only command above, and record the IDs in `fuji.env`.

## Verified locally (2026-11-21)

- Local network (CLI 1.9.6, AvalancheGo v1.14.0): the chain boots, the PoA validator manager
  initializes, and every check in `smoke-test.sh` passes. Permission failures are the precompile
  errors (`not authorized to deploy a contract`, `non-enabled cannot mint`), not missing funds.
- Validator container against Fuji: P-Chain partial sync in about 10 minutes, healthy afterwards.
