# ADR 0037: A reference price per collection center

- Status: proposed (2026-11-23)
- Decided by: Claude, building block 3 (M14) under ADR 0030, which Diego confirmed. It follows
  Diego's point of the same day that the price depends on the collection center the material goes
  to and on what each container takes (ADR 0023, amendment). Not yet confirmed.

## Context
Final payments already follow the real sale: each bag is settled from what its buyer paid
(ADR 0013). But the advance, paid when a deposit is verified, used one reference price per material
for the whole deployment. Two campuses selling to centers that pay differently got the same
advance, and the price table was typed by hand.

## Decision
- **Collection centers are records** (`collection_center`: name, NIT, address, contact) with a price
  per material (`center_price`). Each site sells to one center (`site.center_id`), and a sale can
  name the center that bought (`sale.center_id`).
- **The advance uses the price of the center the site sells to,** for that material; without one it
  falls back to the general table. The advance ratio and the caps are unchanged (ADR 0023).
- **The console suggests a price from the center's own sales:** the median COP per kilogram of its
  confirmed sales in the last 90 days, computed from the buyer's weights. The operator accepts it or
  types another; the record says which (`source`: `sales` or `manual`) and who.
- **Nothing is automatic.** A suggestion never changes a price by itself; prices are money.

## Consequences
- Advances match what each campus's buyer pays, so the final settlement corrects less.
- A site without a center, or a center without a price for a material, behaves as before.
- A collection center portal (M22) can later register its own sales against these records.
