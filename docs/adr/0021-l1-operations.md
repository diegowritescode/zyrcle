# ADR 0021: Operate ZyrcleChain with platform-cli; one validator, fee topped up by hand

- Status: accepted (2026-11-21), recorded 2026-11-22
- Decided by: Claude, while creating ZyrcleChain v2 on 2026-11-21.

## Context
ADR 0002 planned to sign P-Chain transactions with the Avalanche CLI. Avalanche CLI 1.9.7 calls
`platform.getBalance` and `avax.getAtomicTxStatus`, which AvalancheGo v1.15 removed, so it fails on
the paths that create the subnet and convert it to an L1. An L1 validator also pays a continuous
fee on the P-Chain (ACP-77) and stops validating when its balance runs out, as the 2025 chain did.

## Decision
- P-Chain work (subnet, chain, conversion to L1, validator balance) uses `platform-cli` 2.4.0,
  maintained by Ava Labs. Avalanche CLI 1.9.7 is kept only for genesis generation and validator
  manager initialization, whose paths do not use the removed APIs (`infra/l1/README.md`).
- One validator, on the VPS. Its balance is topped up by hand; at the funding of 2026-11-22 it
  lasts until about 2027-03-09, and Diego must be reminded before then.
- The chain's identifiers, contract addresses and roles are recorded in `infra/l1/fuji.env`.

## Consequences
- A second validator is needed before any real value moves (roadmap M7, chain decision).
- If the balance runs out the chain halts; the runbook in `docs/infrastructure.md` covers topping
  it up.

## Amendments
- Supersedes the "Avalanche CLI signs P-Chain transactions" line of ADR 0002.
