# Zyrcle v1: one campus, the full loop

> Status: **planned** (2026-11-22). Phases 0 to 3 and 5 of the rebuild are done or in progress
> ([README](../README.md#status)). This document is the next block of work.

## What v1 means

Today Zyrcle pays residents for depositing. The money comes from seed capital, because nothing
happens to the material after it enters the container: nobody collects it, nobody sells it.

**v1 is Zyrcle closing its loop at least once, on a university campus:** material weighed at the
source, collected, sold to a collection center, the sale reconciled with the bank, every
participant settled from what the buyer actually paid, part of it spent on campus, and a monthly
impact certificate the host can verify on its own.

### Why a university first

- **The host gets something back.** The institution gives space, power and staff attention. In
  return it gets a share of every sale and a verifiable impact report it can use in sustainability
  rankings and reports.
- **Dense, recurring users.** Students and staff pass the same spot every day, and a campus has its
  own merchants (cafeterias, stationery shops) where ZYR can be spent.
- **Several campuses, one institution.** The model scales from one site to many without a new
  agreement each time.
- **Builders on site.** Electronics and mechatronics students can build and maintain the weighing
  station as coursework.

## Principles

- Every milestone ships to the live demo and runs on the simulator until hardware exists. Nothing
  waits for the hardware.
- Every figure a host, buyer or producer sees can be traced to signed device readings and on-chain
  events.
- **One gram, one claim.** The same tonne must not be claimed twice: by a producer for its
  packaging obligation, by a recycler organization for its utility report, and by a host for its
  impact certificate. The ledger records who claimed what.
- Each milestone starts with an ADR and ends with its operator screens.

## Milestones

```
M1 Hosts and sites ──► M2 Collection ──► M3 Sale and settlement ──► M6 Spending on campus
        │                    │                    │
        └──────────────► M5 Impact certificates ◄─┘
M4 Operations console: grows with every milestone (sign-in first)
M7 Pilot readiness: before any real person or peso
H  Weighing station: hardware track, in parallel
```

### M1. Hosts and sites
- **Why:** today a container belongs to a "residence". A university is one host with several sites,
  and the host is a party to the money, the reports and the agreement.
- **Scope:** a `host` (the institution) owns `sites` (today's residences: a campus, a building, a
  residential complex). Participants keep a single account across sites. Each site has its own
  hours, turns and containers. The public dashboard shows a host's totals and each site's.
- **Done when:** the demo shows a university host with two campuses, each with its own containers,
  turns and dashboard, and existing data is migrated without loss.
- **Decision:** ADR 0011, hosts and sites.

### M2. Collection (phase 4a)
- **Why:** the material has to leave the container with its weight and origin intact.
- **Scope:**
  - A collector role with its own screen in the app.
  - Bags tagged with a QR, one material per bag.
  - An emptying recorded by the container's own scale, so collectors never declare weights. This
    is a new device message in the protocol and the simulator.
  - Container mass balance: deposits since the last emptying against the weight removed, with an
    incident when they disagree beyond tolerance.
- **Done when:** in the demo, a collector empties two containers into bags. Each bag knows which
  deposits, and so which grams from which participants, it holds. A tampered emptying opens an
  incident.
- **Decision:** ADR 0012, collection and bags.

### M3. Sale, reconciliation and settlement (phase 4b)
- **Why:** this is the promise. Participants are paid from what the buyer paid, not from seed
  capital.
- **Scope:**
  - Record a sale from the buyer's scale ticket. At level 0 an operator types it from a photo;
    reading the photo with a vision model comes later.
  - The sale is confirmed only when the operator matches it to the bank deposit.
  - Bag mass balance: grams put in against the buyer's kilograms, within a moisture tolerance.
  - Settlement through the Treasury functions that already exist (`recordSale`,
    `settleResidents`, `payCollector`). Each participant's share is pro rata to their grams in the
    bag, minus the advance already paid.
  - **A host share.** The Treasury splits each sale between residents, collector and operations;
    hosts become a fourth party. This needs a new Treasury version, redeployed on Fuji.
- **Done when:** the demo runs deposit → emptying → bag → sale → bank match → settlement end to
  end. Every participant, the collector and the host receive ZYR backed by that sale. The supply
  invariant still holds in the invariant tests.
- **Decision:** ADR 0013, sale, reconciliation and the host share.

### M4. Operations console
- **Why:** everything an operator does today goes through the API with a shared token.
- **Scope:** operator sign-in with named accounts and roles instead of the shared token. Screens
  for the review queue, hosts and sites, containers and devices, prices, collections and
  incidents, sales and bank matching, settlements, and the Treasury. Built in `apps/web`, in the
  hackathon design.
- **Done when:** a pilot can run for a month without anyone using the API by hand.
- **Decision:** ADR 0014, operator accounts and the console.

### M5. Impact certificates
- **Why:** a host's reason to say yes, available from the first month.
- **Scope:**
  - Monthly certificate per site and per host: kilograms recovered per material and the CO2e
    avoided, from a published, cited set of emission factors per material.
  - The month's deposits are anchored on chain (a Merkle root), so a public page can prove that a
    certificate matches the signed readings.
  - The claim ledger: the certificate records that the host claimed those grams for impact
    reporting.
  - Exports a sustainability office can use.
- **Done when:** a host downloads a certificate, opens its verification link and sees it check out
  against the chain. A second certificate over the same grams is refused.
- **Decision:** [ADR 0027](adr/0027-impact-certificates.md), impact certificates. Built in block 2.
- **Not in v1:** tradable carbon or plastic credits. They need an approved methodology, an
  accredited third-party audit, registration (RENARE in Colombia) and a scale no single campus
  reaches. The path is one Zyrcle program aggregating every site, with revenue shared with the
  hosts. M5's data and claim ledger are built so that program can use them unchanged.

### M6. Spending on campus (closed loop)
- **Why:** a balance nobody can spend stops people from coming back.
- **Scope:**
  - A merchant screen that shows a payment QR for an amount.
  - The participant pays from their smart account with a signed `Execute`; a relayer pays the gas.
  - The merchant redeems ZYR for pesos with the Treasury, recorded by the operator.
  - Only businesses go through KYC.
- **Done when:** in the demo, a participant buys something at a simulated campus merchant, and the
  merchant's redemption appears in the Treasury and the reconciliation.
- **Decision:** [ADR 0029](adr/0029-closed-loop-payments.md). Built in block 2; needs the Treasury redeployed.

### M7. Pilot readiness
- **Why:** none of the above should touch a real person's data or money without this.
- **Scope:**
  - Postgres backups, tested by restoring them.
  - Monitoring and alerts for the API, the broker, the validator and the Treasury reserve.
  - A privacy policy and consent at sign-up (Colombian data protection law, Ley 1581 de 2012) and
    terms of use.
  - Legal review of how ZYR is presented: closed-loop points redeemable on campus, not electronic
    money.
  - The app on Google Play's internal testing track.
  - Static analysis of the contracts, and a review of how the oracle and guardian keys are held.
  - A decision on the chain for real value: Fuji, or an L1 on mainnet and what it costs per month.
- **Done when:** the checklist is complete and the host has approved the pilot.
- **Decision:** [ADR 0028](adr/0028-pilot-readiness.md). Built in block 2: backups with a restore check, health and alerts, consent, production switches, Slither review. Waiting for Diego: cron, off-site copy, lawyer, Play account, chain decision.

### H. Weighing station (hardware track, in parallel)
- **Why:** an autonomous container with a camera and NIR is the long-term design, but the pilot
  needs something cheaper and repairable.
- **Proposal:** a staffed weighing station first. A load cell, a microcontroller with a secure
  element, a small display and a lock, speaking the existing device protocol, so nothing else
  changes. The person staffing it, ideally a professional recycler, does the material check that
  the sensors do in the simulator.
- **Done when:** a physical station replaces one simulated container in the demo, with no change to
  the API.

## Decisions still open

| Decision | Default until decided |
|---|---|
| Staffed station or autonomous container for the pilot | staffed station |
| Host share of each sale | set in ADR 0013 |
| Emission factor source for certificates | set in the certificates ADR, cited |
| Who audits the legal framing of ZYR | needed before M7 closes |
| Chain for real value | decided in M7 |

## Out of scope for v1

Tradable carbon or plastic credits (v2, aggregated across sites), cash-out for participants,
collector route optimization, and reports for packaging producers (extended producer
responsibility) and recycler organizations (the SUI). The claim ledger from M5 prepares for the last
two.
