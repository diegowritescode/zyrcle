# ADR 0002: Own Avalanche L1 with ZYR as the native coin

- Status: accepted (2026-11-21)

## Context
The hackathon team created an L1 (`ZyrcleChain`, May 2025), but the app never used it: it ran on
Fuji C-Chain. The L1's only validator later went inactive when its balance ran out, and the
genesis and node keys were not kept.

## Decision
Create ZyrcleChain v2: a Subnet-EVM L1 on Fuji whose native coin is **ZYR (1 ZYR = 1 COP)**.

- NativeMinter: only the Treasury contract mints.
- ContractDeployerAllowList: only the operator deploys contracts.
- FeeManager: near-zero fees. RewardManager: fees go to the treasury.
- Warp enabled from genesis.
- The validator runs on the operator's VPS (`avalanchego` with `--partial-sync-primary-network`).
  P-Chain transactions are signed by a Fuji-only key generated on that VPS.
- Genesis, node config and setup scripts live in `infra/l1` so the chain can be recreated.

## Consequences
- Residents never buy gas: the coin they are paid in is the gas token, and the backend sends most
  transactions.
- The money supply is controlled by contract rules that anyone can audit.
- A single validator is a single point of failure. That is acceptable on testnet. In production
  the validators would be the real stakeholders (collection centers, recycler organizations,
  the municipality).
- The VPS sits at the documented minimum for a low-throughput L1 node (2 cores, 4 GB RAM). Memory
  limits per container, monitored in the existing Grafana.
