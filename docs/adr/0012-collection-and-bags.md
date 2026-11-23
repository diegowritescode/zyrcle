# ADR 0012: Collection and bags

- Status: accepted (2026-11-22)
- Decided by: Claude proposed in v1 block 1; Diego answered "sí, ok, te autorizo" to the list of
  block 1 decisions on 2026-11-22.

## Context
Material entered containers and stayed there. To pay participants from what a buyer pays (ADR 0003,
ADR 0013), every gram sold must be traced back to the deposits it came from, and nobody along the
way should be able to declare a weight. A container may accept more than one material (PET and
HDPE share one in the demo), while a buyer pays per material.

## Decision
- **Collectors are participants with a role.** The operator names a participant's account a
  collector. The same app shows them a collection screen; they are paid from the same smart
  account (the collector's share of each sale, ADR 0013).
- **Bags carry a printed QR, one material each.** The operator creates bags in batches, each with a
  short code (`zyrcle://b/<code>`) and a material. A bag is `open` while it is being filled and
  `sealed` when the collector closes it for delivery. The first collector to fill a bag is its
  collector; nobody else can add to it.
- **An emptying is a collection: the container's own scale weighs every bag.** The collector scans
  the container's rotating QR like anyone else, and the container opens. The protocol does not
  change: to the container, a collection is one more session id. Then, for each bag, the collector
  scans the bag, takes that material out, and taps "done". The grams in that bag are the scale's
  reading before minus the reading after, both signed by the device. Material that is not
  recyclable (a stone in the PET bin) goes out as **residue**, weighed the same way but put in no
  bag. Closing the lid takes the final measurement.
- **Deposits are traced into bags when the lid closes.** Every credited deposit made in that
  container since its previous collection, whose declared material matches a bag filled in this
  collection, is linked to that bag. Deposits of a material nobody bagged stay unlinked: the
  material is still inside and is picked up next time.
- **Two mass balances, each with a tolerance.** The tolerance is the larger of 50 g and 2 %.
  1. *Container:* the weight when the collection opens must equal what was left after the previous
     collection plus what every deposit since then added (final reading minus tare, paid or not:
     rejected material is still inside). For a container never collected, the starting point is
     the tare of its first deposit. A gap means something went in or out outside a session.
  2. *Collection:* what left the container (opening weight minus closing weight) must equal the
     sum of the bags and the residue. A gap means material left without being weighed into a bag.
  A breach opens an **incident** that names the container, the collection and the bags involved.
  The operator resolves it with a note. A bag tied to an open incident cannot be sold or settled
  (ADR 0013).
- **One session at a time per container, deposits and collections alike.** Both lock the
  container row before checking for the other, so they cannot race.
- **The simulator keeps what is inside.** It tracks the contents per item kind and saves them, so a
  restart does not change what the container holds: a real container does not forget its contents
  when it reboots. Its control panel gains "take out" for the demo, standing in for the collector's
  hands, as it already stood in for the participant's.

## Consequences
- Collectors never type a weight. The weight of a bag comes from the same signed scale readings as
  the deposits; the buyer's scale checks it again at the sale (ADR 0013).
- If the collector takes out two materials before tapping "done", both land in one bag. The app
  asks for one material at a time, and the buyer's scale catches what slips through.
- Deposit and collection readings share the same device messages. A collection that never closes
  expires like a deposit session; its incomplete bags keep what was measured so far.

## Details decided while building it (v1 block 1, same confirmation)
- **Bag codes** are 8 Crockford base32 characters (no I, L, O or U), so they can be typed from a
  label when the camera fails; the QR is `zyrcle://b/<code>`.
- **A collection left idle** closes after 10 minutes without the scale moving (a deposit closes after
  1): a collector bags several materials one after another.
- **The demo keeps two empty bags per material** ready, standing in for printed labels, topped up on
  every seed.

## Amendments
- **2026-11-22, Claude (a fix, part of block 1):** a fill whose scale readings differ by less than
  10 g counts as empty. Readings carry a few grams of noise either way, and an "empty" bag could be
  sealed; 10 g is the same threshold that tells material is going in. Commit `65f9366`.
- **2026-11-22, Claude (ADR 0013):** each material goes into a single bag per collection, so a
  deposit is settled from exactly one sale.
- **2026-11-22, Claude (documentation review):** "Deposits are traced into bags" links every deposit
  whose material is inside, credited or not (`verified`, `approved`, `review`, `rejected`), because
  rejected material leaves with the rest. Only credited deposits are paid when the bag is sold
  (ADR 0013), and a bag waits while one of its deposits is in review.
- **2026-11-22, Claude (documentation review):** a collector role given to a phone that is waiting
  to recover an account moves to that account when the recovery completes.
