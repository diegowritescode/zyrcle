# ADR 0036: Split modules by responsibility, not by line count

- Status: proposed (2026-11-23)
- Decided by: Claude, building block 3 (M13) under ADR 0030, which Diego confirmed. Not yet
  confirmed. It narrows M13's first target ("no module over about 400 lines").

## Context
Six backend modules had grown past 550 lines: `models.py` (870), `recovery.py` (768), `sessions.py`
(613), `collection.py` (582), `api.py` (572) and `chain.py` (569). The roadmap asked for none above
about 400.

## Decision
- **Split what mixed responsibilities:**
  - `models.py` became the package `models/`, one module per area (places, participants, deposits,
    money, messaging, collection, sales, operators, impact, payments) on a shared `base.py`. The
    package re-exports every name, so `from .models import Host` still works. The schema is the
    same: 32 tables, and `alembic check` finds no difference.
  - `recovery.py` became `email_codes.py` (codes and the recovery email), `recovery.py` (starting,
    cancelling and showing a recovery) and `recovery_worker.py` (the chain steps).
  - `api.py` became `api.py` (participant routes), `deps.py` (settings, the session service, the
    calling resident or operator) and `setup_routes.py` (hosts, sites, devices, containers, prices,
    the review queue).
- **Keep whole what is one cohesive class:** `sessions.py` (the deposit state machine's service),
  `collection.py` (the collection service) and `chain.py` (the client of the contracts). Each is
  one class with private helpers that call each other; cutting it across files to reach a line
  count would scatter one state machine and hide more than it shows.
- **No behavior changes:** the 106 backend tests and the end-to-end journeys run before and after.

## Consequences
- Each file now reads as one subject, and a change to recovery or setup routes touches one place.
- Three modules remain between 550 and 620 lines, on purpose.
