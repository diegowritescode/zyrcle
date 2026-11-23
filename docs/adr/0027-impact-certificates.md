# ADR 0027: Impact certificates for hosts

- Status: proposed (2026-11-22)
- Decided by: Claude proposed in v1 block 2 (M5); Diego asked for carbon certificates for the host
  institutions on 2026-11-22. Not yet confirmed.

## Context
A host lets containers stand on its sites. Besides a share of each sale (ADR 0013), it wants
something it can show: a sustainability office reports kilos recovered and emissions avoided, and
universities compete in rankings on it. Tradable carbon credits need an approved methodology, an
accredited audit and scale, so they wait for v2 (ADR 0026). What v1 can give is a monthly
certificate whose every gram anyone can check.

## Decision
- **A certificate covers one host (or one of its sites) and one calendar month**, in the deployment's
  time zone. An operator issues it from the console.
- **It counts only material that reached a buyer.** A deposit enters a certificate when its bag's sale
  settled in that month (ADR 0013), not when it was dropped in. Its grams are the verified grams of
  the deposit. Deposits rejected or still in review never count. Material deposited but not sold yet
  is shown on the dashboard, without emissions, and waits for a later certificate.
- **Emissions avoided use EPA WARM version 16** (December 2023), the net emission factors of
  recycling against landfilling, the usual end in Colombia (WARM documentation, chapters on glass,
  metals, paper products and plastics: exhibits 1-4, 2-7, 3-7 and 5-3). Per kilogram of material,
  in grams of CO2e avoided:

  | Material | WARM category | Recycling | Landfilling | Avoided (MTCO2E/short ton) | g CO2e per kg |
  |---|---|---|---|---|---|
  | PET | PET | −1.04 | 0.02 | 1.06 | 1,168 |
  | HDPE | HDPE | −0.76 | 0.02 | 0.78 | 860 |
  | metal | Aluminum Cans | −9.13 | 0.02 | 9.15 | 10,086 |
  | glass | Glass | −0.28 | 0.02 | 0.30 | 331 |
  | cardboard | Corrugated Containers | −3.14 | 0.18 | 3.32 | 3,660 |
  | paper | Mixed Paper (general) | −3.55 | 0.07 | 3.62 | 3,990 |

  One short ton is 907.185 kg, so 1 MTCO2E per short ton is 1,102.3 g per kg; values are rounded to
  whole grams. The table is versioned (`warm-v16`) and every certificate names the version it used.
  WARM models the United States; the certificate says the figure is indicative, not a carbon credit.
- **One gram, one claim.** Issuing a certificate claims the attribute `co2e` of each deposit in it
  (table `impact_claim`, unique per deposit and attribute). A deposit already claimed cannot enter
  another certificate, so the same tonne is never reported twice. Other attributes (packaging
  recovered for a producer, tonnage for the SUI report) can be added later without touching these
  claims.
- **Anyone can verify it.** Each deposit is a leaf `sha256("<deposit id>|<material>|<grams>")`; the
  leaves, sorted, form a Merkle tree where each parent is `sha256` of its two children in sorted
  order. The root is anchored on ZyrcleChain in a plain transaction from the Treasury operator key to
  itself, whose data is `ZYRCLE-CERT-1` followed by the certificate id and the root. The public page
  recomputes the root from the published leaves in the browser and compares it with the data of that
  transaction, read from the public RPC. No contract is needed, and the operator key's signature
  says who issued it.
- **Anchoring goes through an outbox.** The certificate and its claims are written in one
  transaction; a worker sends the anchor transaction and records its hash.
- **Public, with no personal data.** The page shows totals, the factor table and the leaves
  (deposit ids, materials, grams), which identify no person. A printable view and a CSV of the leaves
  are what a sustainability office files.

## Consequences
- A host sees its numbers grow only as bags are sold, which is slower but defensible.
- Changing the factors means a new table version; certificates already issued keep theirs.
- The claim ledger is what a later carbon or plastic credit program (v2) builds on.
