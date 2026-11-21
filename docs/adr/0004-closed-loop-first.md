# ADR 0004: Closed loop first, built so a fiat ramp can plug in later

- Status: accepted (2026-11-21)

## Context
Turning ZYR into pesos for each resident needs a regulated partner and KYC. A token redeemable for
pesos at a fixed value is close to electronic money.

## Decision
- Residents spend ZYR with partner merchants (for example, the building's administration fee or
  local shops).
- Merchants redeem ZYR for COP with the treasury. KYC applies to businesses only.
- The API defines a `RampProvider` port. The first implementation is the manual treasury process.
- Warp is enabled in the genesis, so a later bridge to C-Chain does not require a new chain.

## Consequences
- No consumer cash-out at launch.
- A ramp provider is an adapter, not a redesign.
- Get legal advice before any real-money launch.
