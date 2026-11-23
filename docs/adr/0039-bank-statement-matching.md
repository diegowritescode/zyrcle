# ADR 0039: Matching the bank statement to sales and redemptions, one click each

- Status: accepted (2026-11-23)
- Decided by: Claude, building block 3 (M16) under ADR 0030, which Diego confirmed. Diego confirmed
  it on 2026-11-23: "confirmo todos los adrs".

## Context
Every sale waits for its bank match before anything goes on chain (ADR 0013), and every redemption
waits for the operator's transfer (ADR 0029). The operator read the bank's website and typed each
reference and amount by hand.

## Decision
- **The operator uploads the statement** exported from the bank's website, CSV or Excel. Columns are
  found by their headers (fecha, descripción, referencia or documento, valor, or separate crédito and
  débito), so no single bank's layout is assumed; the separator is the one that splits the most
  lines into columns; Colombian numbers and the usual date formats are understood. A movement seen
  in an earlier statement is recognised by its fingerprint and kept once.
- **The API proposes, each movement and each target once, best first.** A credit for a sale waiting
  for its match: the same amount, between a day before and ten days after the sale, more points for
  a closer date, the ticket number or the buyer's name in the description. A debit for a redemption
  waiting for its transfer: the same amount, up to ten days after the request, more points for the
  merchant's name or tax id.
- **A person confirms each match with one click**, which does exactly what confirming by hand does
  (the same amount rule, the movement's reference as the bank reference) and records who matched the
  movement. Nothing is confirmed automatically.
- **No bank API.** Open banking in Colombia is not usable for this yet; exports work with any bank.

## Consequences
- The bank match becomes uploading a file and pressing a button per movement.
- A bank whose export has no headers is refused with a reason; one real export from the bank Zyrcle
  uses is the best test, and its layout can be added if needed.
- The end-to-end journey confirms its sale and its merchant's redemption from statements.
