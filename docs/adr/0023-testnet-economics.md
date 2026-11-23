# ADR 0023: Testnet money: simulated seed capital and test prices

- Status: accepted (2026-11-22), recorded 2026-11-22
- Decided by: Diego chose the seed amount; Claude set the test prices and advance limits.

## Context
On Fuji, ZYR has no real value, but the Treasury still mints only against recorded pesos
(ADR 0007), so advances need some backing to be paid.

## Decision
- The Treasury records **1,000,000 COP of simulated seed capital** (reference
  `keccak256("testnet-simulated-seed")`), clearly labelled as simulated in `chain/README.md`.
- Advances: 50 % of the reference price per kilo, at most 5,000 COP per deposit and 20,000 COP per
  participant per UTC day (contract limits and `advance_ratio_bps`).
- Demo reference prices (COP/kg): PET 1,000, HDPE 1,000, metal 4,000, glass 200, paper 400,
  cardboard 300. They are test values, not market data.

## Consequences
- None of these numbers may be shown as real economics. A pilot with real money needs real prices
  from confirmed sales (architecture, section 8) and a legal review (roadmap M7).
- Redeploying the Treasury (ADR 0013) records the simulated seed again.
