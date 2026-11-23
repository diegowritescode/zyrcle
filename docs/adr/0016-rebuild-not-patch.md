# ADR 0016: Rebuild the hackathon project instead of patching it

- Status: accepted (2026-11-21), recorded 2026-11-22
- Decided by: Diego set the goal (bring it to a senior level, working completely for what it was
  made for, with hardware that plugs in later without redoing anything); Claude proposed the
  approach.

## Context
Zyrcle won a one-day hackathon in May 2025 (first place and most side prizes). The build was a
demo: the backend served hard-coded data, the contracts in the repository were rebuilt from their
ABI in June 2026 because the originals were lost, the app never used the L1 it had created, a
Pinata secret sat in a public `VITE_*` variable, and no container was ever built. Nobody had used it.

## Decision
- Rebuild it properly in a new monorepo (ADR 0001), keeping the hackathon state at tag
  `v0-hackathon`, instead of patching the demo.
- Frame the product as **verifiable traceability of recovered tonnage**, the problem behind the SUI
  report and producers' packaging obligations (architecture, section 1), not as a crypto app.
- Simulate only the hardware, with a simulator that speaks exactly the protocol a real container
  will speak (ADR 0005, `docs/device-protocol.md`), so hardware replaces it without other changes.
- Build in phases (README, "Status"), each one deployed and tested before the next.

## Consequences
- Most hackathon code was replaced; its visual design was kept (ADR 0018).
- Zyrcle must not be presented as a product in operation while no container exists: it is a
  working system on simulated hardware and a testnet.
