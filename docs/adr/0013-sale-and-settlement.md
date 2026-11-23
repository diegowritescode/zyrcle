# ADR 0013: Sale, bank match and settlement, with a share for the host

- Status: accepted (2026-11-22). The share percentages are a default for Diego to confirm.

## Context
Participants were paid an advance from seed capital (ADR 0003). The rest of the promise, paying
them out of what the buyer actually paid, needs four things: the sale of each bag recorded from the
buyer's own scale, the money seen in the bank, each deposit's part computed from the traceability
data (ADR 0012), and the Treasury minting each part. The host that lets containers stand on its
sites should also get something back ([roadmap](../roadmap-v1.md)).

## Decision
- **A sale is the buyer's ticket, one line per bag.** The operator records the buyer, the ticket
  reference and date, and for each bag the buyer's weight and the pesos paid for it (rollout level 0
  of architecture section 7: typed from the photo). Only sealed bags can be sold, and not while an
  incident names them. The ticket's canonical JSON is hashed into the evidence stored on chain.
- **Bag balance.** The buyer's weight must match the bag's weight, within the larger of 100 g and
  5 % (moisture, labels, a little rejected material). A breach opens a `bag_balance` incident; the
  line is recorded but does not settle until the operator resolves it.
- **Confirmed only when the money arrives.** The operator enters the bank reference and the amount
  received, which must equal the ticket's total. Nothing is recorded on chain before that.
- **One on-chain sale per bag.** Its id is derived from the line's id. For each line a worker, in
  order and checking the chain before every step so a retry never pays twice:
  1. `recordSale` with the backend's operator key;
  2. `settleResidents`, in chunks: each credited deposit in the bag gets the residents' part pro rata
     to its verified grams, minus the advance it already got (the contract subtracts it);
  3. `payCollector` to the account of the collector who filled the bag;
  4. `payHost` to each host whose sites the bag's material came from, pro rata to the grams from
     each, at the host's payout address. A host without an address yet waits; its part is paid when
     the address is set.
  Amounts are whole pesos, rounded down; the dust stays unminted in the sale's parts.
- **A line waits rather than guess.** It does not settle while a deposit in its bag is still in
  review, or while an advance for one of them is being paid.
- **Each deposit is in exactly one bag.** A collection takes each material into a single bag, so
  a deposit's grams are never split across two sales (the contract settles a deposit once).
- **Shares, by default:** residents 65 %, collector 15 %, host 10 %, operations 10 % (before:
  70 / 15 / 0 / 15). The Treasury gains `payHost` and a host part per sale; it is redeployed.
- **The operator key is now online.** Recording a sale needs `OPERATOR_ROLE`. The backend holds that
  key and uses it only after a named operator confirmed the bank match in the console. A leaked key
  could record fake sales and back new ZYR with them; the admin can revoke the role at once, every
  sale carries its evidence hash, and the bank reconciliation would not match.
- **Participants are told.** A deposit that receives more than its advance gets a push notification
  with the amount.

## Consequences
- ZYR in circulation is backed by seed capital plus the distributable parts of sales whose pesos
  reached the bank; the supply invariant is unchanged and its invariant tests now cover hosts.
- A collector who wants a second bag of the same material must finish the collection and start
  another. Splitting a deposit across bags is left for later.
- The Treasury on Fuji must be redeployed for the host share. Its seed capital is recorded again;
  advances already paid stay where they are.
