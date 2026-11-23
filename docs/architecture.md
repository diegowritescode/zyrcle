# Zyrcle architecture

> Status: **rebuild in progress.** The one-day hackathon build (May 2025) is preserved at tag
> `v0-hackathon`. This document is the target design. Sections marked *planned* are not built yet.

## 1. Problem

In Colombia, recycler organizations report the tonnage they recover to the national utilities
information system (SUI) every month, and that report decides how much they are paid through the
waste-collection tariff. The reported figures have been publicly questioned. Packaging producers
are also required to prove how much of their packaging was recovered (Extended Producer
Responsibility, Res. 1407/2018 and amendments).

Both problems need the same thing: **tonnage that can be verified from the source.** Zyrcle measures
recyclable material at the moment a household deposits it, follows it to the buyer, and pays the
household out of what the buyer actually paid.

## 2. Two mirrored chains

```
MATERIAL  deposit ──► container ──► collector bag ──► buyer's scale (collection center)
            grams        grams          grams             kg + COP/kg
                                                              │
MONEY     resident ◄── settlement ◄── treasury (L1) ◄── COP payment to the operator's bank
```

Every ZYR in circulation is backed by material that was weighed and sold, and by pesos that were
received.

## 3. Actors

| Actor | Role |
|---|---|
| Resident | Deposits material at a container and gets paid in ZYR, shown as Colombian pesos. Also called a participant: on a campus they are students and staff. |
| Host | The institution whose sites hold the containers: a university, a residential complex, a business ([ADR 0011](adr/0011-hosts-and-sites.md)). Gets a share of each sale and the impact reports. |
| Container | Device with scale, fill sensor, metal sensor, camera, lock and a small display. Simulated until hardware exists. |
| Collector | Empties containers into bags tagged per material and delivers them to a collection center. |
| Collection center | Buys the material and pays the operator in COP. External party with its own scale. |
| Operator | Runs Zyrcle: reviews flagged deposits, records sales, reconciles bank payments. |
| Partner merchant | Accepts ZYR from residents and redeems it with the treasury (closed loop). |

## 4. Components

| Path | Component | Notes |
|---|---|---|
| `apps/mobile` | Resident app (Expo, built) | Scans the container's rotating QR, shows the live session, balance in COP, hourly turns, push notifications ([ADR 0008](adr/0008-push-notifications.md)). Embedded wallet: key in device secure storage, no seed phrase shown; the ZYR lives in a smart account the key controls, recoverable on a new phone through a verified email ([ADR 0010](adr/0010-smart-accounts-and-recovery.md)). |
| `apps/web` | Landing, dashboards, operations console | The hackathon UI on real data: hosts' and sites' dashboards, the web resident flow, and `/console` for operators signed in by email code ([ADR 0014](adr/0014-operator-accounts.md)): review queue, incidents, collectors and bag labels, sales with the bank match and the settlement report, hosts and sites, prices, operators. |
| `apps/api` | Backend (FastAPI + Postgres) | Deposit sessions, device link, verification (built). Settlement and ledger come in phase 2. |
| `device/simulator`, `packages/protocol` | Device protocol + simulator (built) | Signed MQTT protocol ([spec](device-protocol.md)); the simulator speaks it exactly as firmware will. |
| `chain/` | Treasury contract (built) | Mints ZYR only against recorded pesos; advances and settlements ([ADR 0007](adr/0007-on-chain-treasury.md)). |
| `infra/l1` | ZyrcleChain v2 (live on Fuji) | Subnet-EVM L1 on Fuji, native coin ZYR, validator on the operator's VPS. |
| `infra/deploy` | Compose stack *planned* | API, worker, Postgres, MQTT broker, web, behind Traefik. |

## 5. Deposit session

One session per container at a time, enforced by the database. On top of that lock, hourly turns
spread residents over the day ([ADR 0009](adr/0009-time-slots.md)): each container takes a set
number of residents per hour, a booked spot is guaranteed, and residents without one get in while
the hour has room.

```
IDLE ─scan─► AUTHORIZED ─unlock─► OPEN ─first reading─► DEPOSITING ─"done" / idle timeout─► CLOSING
                                                                                            │
          PAID ◄─ advance minted ◄─ VERIFIED ◄─ score ≥ threshold ─ MEASURED ◄─ stable reading
                                       ▲                               │
                                       └──── operator approves ◄─ REVIEW (score < threshold)
```

Rules:

- The QR on the container rotates (short-lived nonce on the display). A photo of an old code is useless.
- The phone never talks to the container. The backend opens the lock over MQTT and streams live
  readings to the app over WebSocket.
- Deposited weight = stable reading after the lock closes − tare taken right before unlocking.
- Every device message is signed with the device key (secure element) and carries a sequence
  number. Unsigned, replayed or out-of-order messages are rejected.
- If the resident walks away without tapping "done", the session closes after an idle timeout and
  the measured weight is still credited.

## 6. Material verification

Cheapest signal first, combined into one confidence score:

1. **Density**: added weight ÷ added volume (ultrasonic fill sensor). A stone is roughly 25× denser
   than PET of the same volume.
2. **Inductive sensor** for metal.
3. **Camera + vision model**: checks the declared material and flags contamination.
4. **NIR** only if the budget allows. Polymer-grade NIR needs short-wave infrared sensors that cost
   hundreds to thousands of dollars.

High score: accepted automatically. Low score: goes to operator review. A deposit is never rejected
silently.

## 7. Collection and sale

Collection ([ADR 0012](adr/0012-collection-and-bags.md)) and the sale with its settlement
([ADR 0013](adr/0013-sale-and-settlement.md)) are built; reading the ticket photo with a vision
model is not.

- The container's own scale measures each emptying. Collectors do not declare weights.
- Collectors carry one bag per material, each with a QR. Emptying a container records
  "container C put N grams of material M into bag B": the collector scans the bag, takes that
  material out, and the bag gets the difference between two signed readings. What is not
  recyclable goes out as residue, weighed the same way. When the lid closes, the deposits made
  since the previous collection are linked to it.
- The sale of each bag is recorded from the buyer's scale ticket. Rollout levels:
  0. collector photographs the ticket, a vision model extracts the fields, an operator confirms;
  1. collection-center staff send the photo over WhatsApp;
  2. a smart scale at the collection center using the same device protocol.
- A sale is **confirmed** only when the COP payment shows up in the operator's bank account.

### Mass balance

| Hop | Expected | Tolerance |
|---|---|---|
| Container weight when a collection opens vs. what the previous one left plus every deposit since | equal (same scale) | 50 g or 2 % |
| What left the container vs. the bags and residue weighed | equal (same scale) | 50 g or 2 % |
| Grams put into a bag vs. buyer's weight for that bag | equal | moisture and rejected material |

A breach opens an incident for the operator. Nothing is settled from a bag with an open incident.

## 8. Money

- **ZYR** is the native coin of ZyrcleChain. **1 ZYR = 1 COP.** On chain, 1e18 wei = 1 peso.
- Only the Treasury contract can mint (Subnet-EVM NativeMinter allow list), and only against a
  confirmed sale or a recorded seed-capital deposit.
- **Supply invariant:** total minted ≤ confirmed sales (COP) + seed capital (COP). Enforced in the
  contract and covered by invariant tests. The only ZYR that exists outside that rule is the
  **genesis float**: 100 ZYR given to the L1 admin at genesis to pay gas, published in
  `infra/l1/params.env`.
- **Advance and settlement** (how cooperatives pay farmers):
  - On a verified deposit the resident gets an advance:
    `advance_ratio × reference_price(material) × kg`, capped per resident per day, paid from the
    advance reserve.
  - When the bag is sold, the proceeds are split by shares fixed in the contract
    (residents / collector / host / operations: 65 / 15 / 10 / 10 by default). Each resident's part
    is pro rata to the grams traced from their deposits into that bag; each host's, to the grams
    that came from its sites.
  - Settlement = resident's part − advance already paid. Negative results are absorbed by the
    reserve and never clawed back from residents. `advance_ratio` is tuned from loss history.
- **Reference price** per material = rolling average of the last N confirmed sales.
- **Closed loop first:** residents spend ZYR with partner merchants; merchants redeem ZYR for COP
  with the treasury (business-to-business, with KYC on businesses only). A future regulated ramp
  plugs into a `RampProvider` port in the API. Warp is enabled in the L1 genesis so the chain can
  bridge to C-Chain later without being rebuilt.

## 9. Units

| Quantity | Off chain | On chain |
|---|---|---|
| Weight | integer grams | `uint256` grams |
| Money | integer COP | wei-ZYR (1e18 = 1 COP) |

The hackathon build mixed three conventions (18-decimal "kg", grams and whole kg). That is gone.

## 10. What is simulated

Only the hardware. The device simulator implements the real protocol, including signatures. When a
physical container exists, it replaces the simulator and nothing else changes.

## 11. Not in scope yet

Collector route optimization (phase 5), cash-out for residents, mainnet.
