# ADR 0027: Impact certificates for hosts

- Status: accepted (2026-11-23; proposed 2026-11-22)
- Decided by: Claude proposed in v1 block 2 (M5); Diego asked for carbon certificates for the host
  institutions on 2026-11-22 and chose the IPFS copy (amendment). Diego confirmed it on 2026-11-23: "confirmo 0015, 0027, 0028 y 0029".

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

## Amendments
- **2026-11-22, Diego (a permanent public copy on IPFS, through Pinata):** he recalled that the
  2025 project pinned certificates on IPFS through Pinata ([history](../history.md)) and chose,
  among the options Claude laid out, to pin each certificate's document and write its CID on chain
  ("option A"). Claude designed and built it the same day.
  - **What changes.** Before anchoring, the anchor worker pins the certificate as a JSON document on
    IPFS through Pinata (`pinJSONToIPFS`, CID version 1) and keeps its CID in `certificate.ipfs_cid`
    (migration 0013). The anchor's data becomes `ZYRCLE-CERT-2`, the 16-byte certificate id, the
    32-byte root and the CID as ASCII text. Without a Pinata JWT nothing changes: the worker anchors
    `ZYRCLE-CERT-1` as before.
  - **Why.** The certificate stays checkable if Zyrcle's servers disappear. IPFS names a file by the
    hash of its content (the CID), so the chain says which document it is and any IPFS gateway can
    serve it; a changed byte would give another CID. The document's own leaves rebuild the anchored
    root. A host can keep the file, or pin it itself, and needs nothing from Zyrcle to check it.
  - **The document** (schema `zyrcle-certificate/1`): id, issuer, host, site, period, `issued_at`,
    totals, `by_material`, the factor table with its version and source, the Merkle rule in words, the
    root and the leaves. It is built from the database the same way every time, so pinning it again
    gives the same CID.
  - **No personal data in it.** A copy on IPFS cannot be recalled once others hold it. The document
    leaves out the operator's email (`issued_by`). The leaves carry random deposit ids, and only
    Zyrcle's database links an id to a person: if a participant asks to be deleted (Ley 1581),
    removing that link leaves the id in the copy anonymous. The legal review of ADR 0028 should
    confirm this reading.
  - **Pin first, then anchor.** The CID is stored before the transaction is sent, so a retry after a
    failed anchor reuses it. If Pinata does not answer, the certificate waits in `issued` and the
    worker tries again every 30 seconds; the health report shows the queue as stuck (ADR 0028). Once
    Pinata is configured the worker never anchors without the CID, because an anchor is written once.
  - **Verification in the browser** takes the CID from the anchor transaction, not from Zyrcle's API,
    reads the document from the IPFS gateway, and checks that its leaves give the anchored root. If the
    gateway does not answer, the page still checks against the chain and says the copy could not be
    opened.
  - **Only the JWT** is used (`PINATA_JWT` in `deploy/.env`, placed by Diego over SSH, ADR 0022).
    Pinata's API key and secret pair is not needed. The key should allow pinning only.
  - **Gateway.** Browsers read from `https://gateway.pinata.cloud/ipfs/` by default; it answers with
    `Access-Control-Allow-Origin: *`, and the web page's Content-Security-Policy allows it. A dedicated
    gateway (`<name>.mypinata.cloud`) can replace it by changing `ZYRCLE_IPFS_GATEWAY`,
    `VITE_IPFS_GATEWAY` and `apps/web/security-headers.conf` together.
  - **Limits.** The browser trusts the gateway to return the bytes of that CID; it does not recompute
    the CID, which needs an IPFS library. Anyone in doubt can fetch the same CID from another gateway or
    their own IPFS node. The copy stays online while someone pins it: if Zyrcle's Pinata account
    lapses and nobody else pins it, it can disappear from IPFS, while the anchor and the database
    remain. Pinata's free plan holds about 500 files; at one certificate per host or site a month,
    that lasts years.
  - **Code:** [`ipfs.py`](../../apps/api/src/zyrcle_api/ipfs.py),
    [`impact.py`](../../apps/api/src/zyrcle_api/impact.py) (`AnchorWorker`),
    [`domain/impact.py`](../../apps/api/src/zyrcle_api/domain/impact.py) (`anchor_data`,
    `certificate_document`),
    [`certificate.ts`](../../packages/client/src/certificate.ts) (`anchorData`, `parseAnchor`),
    [`CertificatePage.tsx`](../../apps/web/src/pages/CertificatePage.tsx).
