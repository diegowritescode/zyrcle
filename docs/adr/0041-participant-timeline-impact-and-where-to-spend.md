# ADR 0041: The participant follows each deposit to the sale, sees their impact and where to spend

- Status: accepted (2026-11-25)
- Decided by: Claude, building block 4 (M18) under ADR 0030, which Diego confirmed. Diego asked to
  start M18 and M19 on 2026-11-24: "listo, empieza con eso". Diego confirmed it on 2026-11-25:
  "si, confirmo, documenta todo".

## Context
A participant saw each deposit with its advance and, once the bag was sold, one figure for what came
on top. Between the deposit and that figure there were weeks with no news: the bag being filled,
sealed, sold to a collection center, the center paying the campus, the settlement on chain. The ZYR
they earned could only be spent at campus merchants, but nothing told them which merchants there were
or where to find them. Their impact existed only in the host's monthly certificates (ADR 0027).

## Decision
- **Each deposit carries its steps** in `GET /v1/me`, in order: `deposited`, `verified`, `advance`,
  `collected`, `sold`, `paid`. Each step has a status (`done`, `pending`, `failed` or `skipped`), the
  time it happened and, where it applies, an amount, a transaction and a short detail:
  - `verified` is `done` when the deposit was verified or approved after review, `pending` while in
    review, and `failed` when rejected. A rejected deposit skips every later step.
  - `advance` is the advance payment and its transaction; `skipped` when the deposit got none (no price
    for its material, or an amount that rounds to zero; ADR 0003, ADR 0037).
  - `collected` is the close of the collection that took its material out (ADR 0012).
  - `sold` is the first sale that includes a bag holding its material: the date on the ticket and
    the buyer's name. A sale cannot be deleted once recorded, so this step never goes back.
  - `paid` is the settlement of the deposit's share (ADR 0013): `done` once every sale line holding
    its material settled, with the share and what came on top of the advance, summed over the lines
    (a deposit can end up in two bags when one fills up during a collection). When the advance
    already covered the share, the step says so and the amount on top is zero.
  A deposit is in a bag when the bag got its material in the deposit's collection: the same rule the
  settlement and the certificates use. The figure "on top of the advance" (`settled_cop`) is now the
  sum over every line; before it kept only one line's.
- **Two pushes, not one.** When a sale is recorded, every credited deposit in its bags gets one push,
  `deposit_sold` ("Se vendió tu material…"), once per deposit even if it is in two bags. When the
  settlement pays something on top of the advance, the existing `settlement_paid` push follows. When
  the advance already covered the share there is no second push: the first one said it was sold, and
  the steps show the rest. Deposits still in review when the sale is recorded get no `deposit_sold`;
  if they are approved later they still get `settlement_paid`. Both use the Android channel
  `payments`.
- **Personal impact** at `GET /v1/me/impact`: the participant's verified grams (credited deposits, by
  the month they were made) and sold grams (credited deposits whose bag's sale settled, by the month
  of the first settlement), per material and per month for the last 12 months, plus totals. CO2e
  avoided is computed only on sold grams, with the same WARM v16 factors and the same rule as the
  certificates (ADR 0027), and the apps say it is indicative. This is a view of grams that also
  appear in the host's certificate, not a second claim: nothing is recorded in `impact_claim`, and
  the figure cannot be transferred or sold.
- **Where to spend.** A merchant gets four optional fields the operator fills in the console: its
  site (campus), where it is inside it (`place`, free text such as "Bloque 7, primer piso"), its
  hours (`hours`, free text such as "L-V 7:00 a 18:00") and what it sells (`offer`). `GET
  /v1/merchants` is public and lists active merchants that belong to a host: name, host, site,
  place, hours and what they sell. It never shows the tax id or the account address. The web app and
  the mobile app show the list, grouped by host and site.

## Consequences
- The participant can see where their material is at any moment, and the two pushes cover the two
  moments that bring news: sold and paid.
- `GET /v1/me` makes a few more queries per call (one per step kind, for the 20 deposits it shows),
  never one per deposit.
- Migration `0017` adds the merchant fields. They are free text: no opening-hours logic, no map. A
  map or structured hours can come later without changing the endpoint's shape.
- The personal CO2e figure always matches the certificates' rule, so a participant's figures add up
  to at most what their host's certificates say for the same months.
- Until the new Android build (M23), the installed app keeps showing the old deposit row; the web app
  shows the steps at once.
