# ADR 0003: Pay residents with an advance plus a settlement

- Status: accepted (2026-11-21)

## Context
Real money enters only when a collection center buys the material, days after the deposit, at a
price that depends on material and market. A fixed instant payout can drain the treasury. Paying
only after the sale is honest but makes residents wait.

## Decision
- At a verified deposit, pay an advance of `advance_ratio × reference_price × kg`, capped per
  resident per day, out of an advance reserve funded with seed capital.
- At sale confirmation, split the proceeds by contract-defined shares and settle each resident's
  pro-rata part minus the advance.
- Negative settlements are absorbed by the reserve, never clawed back from residents.

## Consequences
- Keeps the instant reward from the original design.
- Needs seed capital and a reserve policy. `advance_ratio` and the cap become tunable parameters.
- Settlement depends on exact traceability from deposit to bag, which the collection design
  (bags with QR, container-measured emptying) provides.
