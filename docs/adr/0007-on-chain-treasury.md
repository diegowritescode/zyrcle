# ADR 0007: An on-chain Treasury that mints only against recorded pesos

- Status: accepted (2026-11-22)

## Context
ZYR is ZyrcleChain's native coin and 1 ZYR stands for 1 peso. Its credibility depends on one rule:
no ZYR without pesos behind it (ADR 0004). The backend must pay residents automatically, but a
compromised backend must not be able to print money.

## Decision
- A `Treasury` contract is the only address on the NativeMinter allow list.
- `backing` grows only through `recordSeedCapital` and `recordSale` (OPERATOR_ROLE). A sale adds
  only its residents and collector parts; the operations part stays in pesos.
- Every mint checks `minted + amount <= backing`. Foundry invariant tests drive random sequences of
  all operations and assert it, plus that the contract's books equal what the precompile minted.
- The backend holds ORACLE_ROLE: it can pay advances (one per deposit, capped per deposit and per
  resident per UTC day) and settlements, nothing else. Admin can pause payouts.
- Settlement takes each deposit's share of a sale and pays `share - advance`, never less than zero:
  an advance larger than the share is a loss absorbed by the reserve, not clawed back. Shares are
  computed off chain from the traceability data; `reportHash` anchors the published report.
- The backend writes payouts to a transactional outbox in the same database transaction that
  credits the deposit. A worker sends them; on restart it asks the contract (`advanceOf`) whether a
  payment already happened, and the contract refuses a second advance, so retries never pay twice.
- The backend deploys and operates the contract with web3.py from the compiled artifact. CI fails
  if that artifact differs from what `forge build` produces.

## Consequences
- A leaked oracle key can pay at most the daily cap per resident address until an admin pauses the
  Treasury; it cannot raise `backing`.
- Recording a sale is a human (operator) step until bank reconciliation is automated (phase 4).
- Daily caps use UTC days, not Colombian days (UTC-5).

## Amendments
- **2026-11-22 (ADR 0013):** a sale now has a host part too; `backing` grows by the residents',
  collector's and host's parts, and `payHost` pays hosts. Recording a sale is done by the backend's
  operator key after a named operator confirms the bank match.
