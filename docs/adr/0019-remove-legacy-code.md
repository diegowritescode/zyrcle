# ADR 0019: Remove the legacy code, keep it at tag v0-hackathon

- Status: accepted (2026-11-22), recorded 2026-11-22
- Decided by: Claude proposed; Diego approved the plan.

## Context
After the rebuild, three pieces were dead weight: the hackathon API (moved to `apps/api-legacy`), a
minimal live-demo page (`apps/demo`) built before the web app was wired to the new backend, and the
hackathon's Hardhat contracts (`contracts/`), replaced by the Foundry `chain/` (ADR 0007). Keeping
them invited confusion about what is live.

## Decision
- Delete `apps/api-legacy`, `apps/demo` and `contracts/` from `main`.
- They remain readable at tag `v0-hackathon` and in history.

## Consequences
- One backend, one web app, one contracts folder. The README's layout is the truth.
- The old repositories (`zyrcle-backend`, `zyrcle-frontend`) still exist and are not archived yet.

## Amendments
- **2026-11-22, with Diego's approval:** both original repositories got a notice pointing to this
  monorepo and were archived (read-only).
