# ADR 0042: Collectors get fill alerts, a list of what to empty first, and their earnings

- Status: accepted (2026-11-25)
- Decided by: Claude, building block 4 (M19) under ADR 0030, which Diego confirmed. Diego asked to
  start M18 and M19 on 2026-11-24: "listo, empieza con eso". Diego confirmed it on 2026-11-25:
  "si, confirmo, documenta todo".

## Context
A collector learned that a container was full by walking to it. The fill level existed on the site
dashboard, from the latest deposit's distance sensor reading, but it stayed at the last deposit's
value after a collection emptied the container. Collectors were not tied to any host, and they could
see what they collected but not what each collection paid them.

## Decision
- **The fill level comes from the distance sensor** (`fill_mm`, the distance from the sensor down to
  the contents; ADR 0005, docs/device-protocol.md): `100 × (depth − distance) / depth`, between 0 and 100. The
  reading used is the latest one after a lid closed, whether a deposit's or a collection's.
  Collections now keep their own reading (`collection.fill_after_mm`, from the `measurement` message
  the container already sends). A collection that closed after the latest deposit and has no reading
  (older rows) counts as empty. The site dashboard uses the same function, so it no longer shows a
  container full after it was emptied.
- **A collector can belong to one host.** `collector.host_id` is optional and set in the console
  when naming the collector, like a merchant's host (ADR 0029). Without a host, a collector sees and
  is alerted about every host's containers, which is how the pilot works today.
- **The alert.** When a deposit's measurement leaves a container at or above 80 % (setting
  `ZYRCLE_FILL_ALERT_PCT`), each active collector of the container's host, and each active collector
  without a host, gets a push `container_full`: "Contenedor X al 85 %". One push per collector per
  fill cycle (between two collections), so a full container that keeps receiving deposits does not
  push again until it is emptied. It is written to the notification outbox in the same transaction
  as the measurement (ADR 0008). It uses a new Android channel, `collection`; until the new build
  creates it, Android shows it on the default channel.
- **What to empty first.** `GET /v1/collector` adds the collector's containers (their host's, or all
  of them): fill level, when it was last emptied and how many deposits it got since. Ordered by fill
  level (highest first, unknown last), then by the longest time since it was emptied.
- **Earnings** at `GET /v1/collector/earnings`: each of the collector's closed collections of the
  last 6 months, with the container, the grams that went into bags, what it has paid so far and
  the grams still waiting for a sale; and a total per month (the month the collection closed, in the
  deployment's time zone). What a collection paid comes from the collector's settlement share of
  each sale line (ADR 0013), split among the collections that filled the bag by the grams each put
  in it. A bag filled in one collection gives that collection its whole share.

## Consequences
- Migration `0017` adds `collection.fill_after_mm` and `collector.host_id`.
- Collectors stop walking to half-empty containers; the list tells them where to go.
- Earnings by collection are a split of per-bag shares, so their total always equals what the
  settlement report paid the collector.
- The threshold is one number for every container. A threshold per container, or an alert by
  weight instead of height, can come later if a container type needs it.
- The alert depends on the distance sensor. A container whose sensor fails (no `fill_after_mm`)
  shows "unknown" and raises no alert.

## Amendments
- **2026-11-26 (UTC), deployed with Diego's approval** ("autorizo unir la rama a main y desplegarla
  en produccion"): commit `72a875b`, migration 0017, after a backup. Nothing in the decision changed.
