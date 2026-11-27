# ADR 0046: Hosts get a monthly certificate without asking, goals per site, and ranking figures

- Status: proposed (2026-11-27)
- Decided by: the milestone is M20 of block 4 ([ADR 0030](0030-blocks-3-and-4.md)), which Diego
  accepted with the plan. On 2026-11-27 he asked to build it in this order ("continuemos con tu
  orden en un bloque grande"). Claude chose the rules below. Waiting for Diego's confirmation.

## Context
A host (the university) gets an impact certificate only when an operator issues one in the
console ([ADR 0027](0027-impact-certificates.md)), and receives nothing unless someone sends the
link. The roadmap asked for three things: the previous month's certificate issued and emailed as a
formal PDF without anyone asking; monthly kilogram goals with a comparison between sites; and the
figures a sustainability ranking such as UI GreenMetric asks for, backed by Zyrcle's records.

## Decision

### The monthly report
- **Opt-in per host.** The console sets `monthly_report` and up to ten `report_emails` per host.
  Opting in needs at least one email. Addresses are normalized (trimmed, lowercase, no duplicates).
- **When.** A worker looks every 10 minutes (`ZYRCLE_MONTHLY_REPORT_INTERVAL_S`). From the 1st to
  the 7th of each month, Bogotá time (`ZYRCLE_MONTHLY_REPORT_LAST_DAY`), it makes the previous
  month's report for every host that opted in and does not have one. A host that opts in on the
  15th gets its first report the next month. The worker runs only with email on.
- **What.** One certificate for the whole host (all its sites), issued by the same rules as an
  operator's: material whose sale settled in that month, each deposit claimed once. Its issuer
  reads "el informe mensual automático". If an operator already certified everything, the latest
  whole-host certificate of that month is used instead. If nothing was sold, the report is
  recorded as `empty` and no email goes out.
- **Sent once, after the anchor.** The email waits until the certificate's root is anchored on
  ZyrcleChain (and its public copy is on IPFS when Pinata is configured, since the anchor waits
  for it). A table `monthly_report` keeps one row per host and month: `waiting`, then `sent` or
  `failed` (anchor failed, or no email left on the host); or `empty`.
- **The email** says the month's figures, links the public verification page, and says it counts
  only what went through Zyrcle. The PDF goes as an attachment. The outbox gained an
  `attachments` column; an attachment is cleared once the email is sent or given up on, because
  the PDF can be made again.

### The PDF
- One A4 page, made with reportlab (BSD licence; it brings its own QR code): the host, the month,
  kilograms recovered and sold, CO2e avoided, deposits and people, the table by material, how it was
  counted (only sold material; EPA WARM v16; indicative, not a carbon credit; no deposit in two
  certificates), and how to verify it: a QR to the verification page, the page's address, the Merkle
  root, the IPFS CID, the anchor transaction, and the chain, named as a test network.
- `GET /v1/certificates/{id}/pdf` returns it to anyone, like the certificate itself. The
  certificate page and the console link to it. The verification page's address comes from the new
  setting `ZYRCLE_PUBLIC_WEB_URL` (default `https://zyrcle.deviego.xyz`).
- The PDF presents the certificate; it is not the proof. The proof stays the anchored root and the
  public copy, which the verification page checks in the reader's browser.

### Goals and comparison
- `monthly_goal_kg` on a host and on each site, set in the console; empty means no goal.
- `GET /v1/hosts/{id}/progress` (public, like the dashboard; totals only) returns this month's
  kilograms against the host's and each site's goal, people who recycled, kilograms per person, and
  the last 1 to 12 months (6 by default) for each site. Kilograms here are credited deposits
  counted in the local month they were made, like the dashboard; a person who recycles at two
  sites counts once for the host. The host's panel shows them under "Metas de <mes> y comparación
  entre sedes", sites ordered by kilograms.

### Figures for rankings
- `GET /v1/operator/hosts/{id}/greenmetric?year=` returns an Excel workbook: a summary mapped to
  the Waste (WS) indicators, then sheets by month, by material, and with the year's certificates as
  evidence (verification page, IPFS copy, transaction).
- The indicators were checked on 2026-11-27 in public sources, not in the official questionnaire,
  which could not be read: WS.1 (3R programme: people and deposits), WS.2 (paper and plastic: PET and
  HDPE recycled), WS.4 (inorganic waste treatment: kilograms by material, received and verified,
  and recycled, meaning sold to a collection center). The workbook asks to confirm the indicators
  in the year's questionnaire.
- It says what it covers: only what went through Zyrcle, not the institution's total waste.
  Zyrcle records no campaigns, so the workbook says so instead of inventing them. CO2e is listed as
  informative.

## Consequences
- A host receives its certificate every month without an operator, with something it can print,
  file and verify.
- Migration `0018`: `host.monthly_report`, `host.report_emails`, `host.monthly_goal_kg`,
  `site.monthly_goal_kg`, `email_message.attachments` and the table `monthly_report`.
- New dependencies in the lock file ([ADR 0044](0044-api-dependencies-locked.md)): reportlab 5.1.0
  and Pillow 13.0.0.
- If the chain is down for days, the report waits with it; the console shows it as "Esperando el
  anclaje". After the 7th, a host whose report was never made does not get that month's
  automatically; an operator can still issue the certificate and send the PDF by hand.
- The comparison is by kilograms deposited, not sold: a site's goal moves with what its people
  bring, not with when the collection center pays.
