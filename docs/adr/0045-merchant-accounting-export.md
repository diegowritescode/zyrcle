# ADR 0045: Merchants export their charges and redemptions for their bookkeeping

- Status: accepted (2026-11-27)
- Decided by: the milestone is M21 of block 4 ([ADR 0030](0030-blocks-3-and-4.md)), which Diego
  accepted with the plan. On 2026-11-27 he asked to build it in this order ("continuemos con tu
  orden en un bloque grande"). Claude chose what goes in the file and how it is offered. Diego
  confirmed it on 2026-11-27: "confirmo los adrs y autorizo unir a main y desplegar".

## Context
A campus merchant charges participants in ZYR and turns ZYR into pesos ([ADR 0029](0029-closed-loop-payments.md)).
Their accountant needs those movements with the merchant's tax id and something that ties each one
to the chain and to the bank. Until now the app showed only the last 20 charges and redemptions,
and nothing could be downloaded.

## Decision
- **What goes in.** One row per movement in a range of days:
  - a charge, once it is paid, dated when it was paid;
  - a redemption, once its ZYR left the account (`pending`, `settled` or `refunded`), dated when it
    was requested. The row says whether the pesos were transferred, with the transfer's date and the
    bank's reference, or whether the ZYR came back.
  Charges never paid and redemptions that never reached the chain moved nothing and are left out.
- **The columns:** date, type (Cobro or Canje), status, amount in pesos, concept, Zyrcle's
  reference, the transaction, the transfer's date, the bank's reference, the closing transaction,
  and the merchant's name and NIT. The payer's account is not included: the transaction already
  ties the charge to the chain, and the merchant's books do not need to know who paid.
- **Days are Bogotá's.** `start` and `end` are local days in `ZYRCLE_TIMEZONE`, both included, and
  the dates in the file are local times. The apps pick "today" in Bogotá too, whatever zone the
  device's clock is set to. At most 366 days per export.
- **Two formats.** Excel (`.xlsx`) has a header with the merchant, the NIT, the period and when the
  file was made, the table, and totals: charges paid, redemptions transferred and redemptions
  waiting for their transfer. CSV has the same table: comma-separated, UTF-8 with a byte order mark
  so Excel keeps the accents, for importing into accounting software.
- **Text never runs as a formula.** The concept, the bank's reference and the name are typed by
  people. In the CSV a value that starts with `=`, `+`, `-`, `@`, a tab or a return gets a leading
  apostrophe; in Excel every text cell is typed as text.
- **Where:** `GET /v1/merchant/export?start=&end=&format=csv|xlsx` for the signed-in merchant, in
  the app's merchant screen ("Para tu contabilidad": this month, last month or this year), and
  `GET /v1/operator/merchants/{id}/export` for the console, with any range. On the phone the file
  goes to the share sheet (WhatsApp, Drive, email, the phone's files) through `expo-sharing`; in a
  browser it downloads. A merchant the operator switched off can still export: the movements
  happened, and the books need them.
- **The file's name comes from the API** (`zyrcle-<merchant>-<start>-a-<end>.<format>`) in
  `Content-Disposition`, which the API now lets browsers on the web app's origin read.

## Consequences
- An accountant gets the month in one file, and each row can be checked against the chain (the
  transaction) and the bank (the reference).
- `expo-sharing` and `expo-application` are new native modules, so the export on the phone needs
  the next APK.
- A redemption requested in one month and transferred in the next appears in the month it was
  requested, with the transfer's date in its own column.
- Signed amounts, the payer, and a running balance are not in the file. They can be added if an
  accountant asks.
