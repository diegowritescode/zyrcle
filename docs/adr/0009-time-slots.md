# ADR 0009: Hourly time slots with walk-ins

- Status: accepted (2026-11-22)

## Context
The hackathon design gave residents hourly turns: you came in your hour, scanned, recycled. Today a
container already serves one session at a time (a database lock), so turns are not needed for
correctness. They are needed to spread a residence's residents over the day, to guarantee an hour to
whoever planned it, and to let a residence open its containers only at certain hours.

## Decision
- Slots are whole local hours in the deployment's time zone. Each residence has opening hours
  `[opens_hour, closes_hour)` and a capacity: residents per container per hour (default 20; a
  deposit takes one to three minutes).
- **A booked spot is guaranteed. Walk-ins fill what is left.** A resident who scans without a
  booking gets a spot if the hour has room; that walk-in spot is stored like a booking and counts
  against the capacity. When every spot is taken, only residents holding one can open the container
  (`409 slot_full`). Outside opening hours nobody can (`409 closed`).
- A spot covers every session of that resident at that container in that hour, so recycling PET and
  then glass takes one spot, not two.
- Rules: book on the hour, up to 7 days ahead (today included), at most 3 upcoming bookings per
  resident, cancel any time before the hour ends unless the spot was already used.
- Taking a spot happens under a lock on the container row, in the transaction that creates the
  session or the booking. A partial unique index keeps one live spot per resident, container and
  hour. Two residents can never take the last spot together.
- No-shows are not penalised yet. The data to do it (booked, never used) is kept.

## Consequences
- A residence that does not want turns keeps the default: open all day with 20 spots per hour,
  which a single container never fills, so nobody notices the layer.
- Changing a residence's hours does not cancel bookings already outside them; an operator should
  warn those residents. Notifying them is follow-up work on top of ADR 0008.
- One time zone for the whole deployment (`ZYRCLE_TIMEZONE`). Residences in other zones need a
  per-residence zone first.
