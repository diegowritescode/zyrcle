# Database

This document describes Zyrcle's PostgreSQL database. It covers every table, the code that writes
each one, the rules the schema enforces, and how to change the schema. It is written for engineers
who are new to the codebase.

The code is the source of truth: [`models.py`][models] and the migrations in
[`migrations/versions/`][versions]. If this document and the code disagree, the code wins, and this
document needs a fix. This document describes the schema at migration `0008`.

## Contents

1. [Overview](#1-overview)
2. [Entity-relationship diagrams](#2-entity-relationship-diagrams)
3. [Tables](#3-tables)
4. [State machines](#4-state-machines)
5. [Outbox tables and workers](#5-outbox-tables-and-workers)
6. [Invariants: schema versus code](#6-invariants-schema-versus-code)
7. [Migrations](#7-migrations)
8. [Data that must never be stored](#8-data-that-must-never-be-stored)
9. [Discrepancies found](#9-discrepancies-found)

## 1. Overview

### Engine and access

- The database is PostgreSQL 17. Development, CI and production all use the `postgres:17-alpine`
  image ([dev compose][dev-compose], [CI][ci], [deploy compose][deploy-compose]).
- The API is the only client. It uses SQLAlchemy 2 in async mode with the asyncpg driver
  ([`db.py`][db]). The connection string comes from `ZYRCLE_DATABASE_URL`.
- Sessions use `expire_on_commit=False`, so loaded objects stay readable after a commit.
- Every request and every background job opens its own short transaction. The code does not change
  the isolation level, so it is PostgreSQL's default, READ COMMITTED.
- Rows that must not change during a transaction are locked with `SELECT … FOR UPDATE`.
- Background jobs that several API replicas may run at once add `SKIP LOCKED`. With `SKIP LOCKED`,
  a query skips rows that another transaction has locked instead of waiting for them. Two replicas
  therefore never work on the same row.

### How the schema is created

- Alembic migrations are the only way the schema is created or changed. No code calls
  `metadata.create_all()`.
- `alembic upgrade head` builds or updates the schema. Locally you run it by hand
  ([API README][api-readme]). In production, the `migrate` service in the
  [deploy compose file][deploy-compose] runs it with the API image.
- The test suite drops the `public` schema, recreates it and runs `alembic upgrade head`, once per
  test session (fixture `migrated_db` in [`conftest.py`][conftest]). The database comes from
  `ZYRCLE_TEST_DATABASE_URL`. Its default is the same local database that development uses, so
  running the tests wipes your local data.
- CI applies all migrations to an empty database and then runs `alembic check` ([CI][ci]).
  `alembic check` fails when `models.py` and the migrated schema differ in what it compares. It
  compares tables, columns, column types ([`env.py`][env] sets `compare_type=True`), nullability,
  indexes, unique constraints and foreign keys. It does not compare CHECK constraints or server
  defaults. [Section 9](#9-discrepancies-found) lists a gap this caused.

### Units

| Quantity | Unit | Column names | Examples |
|---|---|---|---|
| Weight | integer grams | end in `_g`, or `grams` | `tare_g`, `deposited_g`, `bag.grams` |
| Distance | integer millimetres | end in `_mm` | `fill_before_mm`, `depth_mm` |
| Area | integer square millimetres | end in `_mm2` | `container.area_mm2` |
| Volume | integer millilitres | end in `_ml` | `added_volume_ml` |
| Money | integer Colombian pesos (COP) | end in `_cop` | `amount_cop`, `share_cop` |
| Price | integer COP per kilogram | `cop_per_kg` | `material_price.cop_per_kg` |
| Device clock | unix milliseconds | `device_ts` | `device_message.device_ts` |
| Confidence | float from 0 to 1 | `score` | `deposit_session.score` |

- `deposit_session.score` is the only floating-point column.
- Advances and prices use `integer`. Sales and settlements use `bigint`.
- ZYR is the native coin of Zyrcle's own Avalanche L1, and 1 ZYR = 1 COP
  ([ADR 0002][adr-0002]). On chain, 1 COP is 10^18 wei (`WEI_PER_COP` in [`chain.py`][chain]). The
  database never stores wei.

### Time and time zones

- Every timestamp column is `timestamptz`. PostgreSQL stores it as an absolute instant.
- The API writes time-zone-aware UTC values (`datetime.now(UTC)`). Server defaults use `now()`.
- A deployment has one local time zone: `settings.timezone` (`ZYRCLE_TIMEZONE`, default
  `America/Bogota`), defined in [`config.py`][config]. Code uses it for:
  - site opening hours (`site.opens_hour`, `site.closes_hour`);
  - booking slots: `booking.starts_at` is the start of a local hour;
  - sale dates: `sale.sold_on` is noon, local time, of the date the operator typed;
  - daily aggregates in [`public.py`][public], which group rows by
    `CAST(timezone(<settings.timezone>, created_at) AS date)`.
- Rate limits on codes use rolling 24-hour windows (`now - 1 day`), not calendar days.
- A payout refused for the Treasury's daily advance cap, and an email refused for Resend's daily or
  monthly quota, wait until the next UTC midnight.

### Naming conventions

- **Tables** are singular and snake_case: `deposit_session`, `sale_line`.
- **Primary keys** are `id uuid`. The API generates them with `uuid4`; there is no server default,
  so a raw SQL insert must supply the id. Exceptions, where a natural key is the identity:
  `device.id` and `container.id` (strings the operator chooses, such as `ctr-0001`),
  `material_price.material`, `auth_nonce.nonce`, `push_token.token`, `collector.resident_id`,
  `device_message (device_id, seq)`, and `session_event.id` (`bigserial`).
- **Foreign keys** are named `<table>_id`. Exceptions: `collector_id` on `bag` and `collection`
  points to `resident.id` (not to `collector`), `new_resident_id` points to `resident.id`, and
  `line_id` points to `sale_line.id`.
- **Logical links without a foreign key:** `settlement.party_ref`, `incident.bag_ids`, and
  `deposit_session.declared_material` matched to `material_price.material`.
- **Lifecycle columns** are called `state` when device events drive the lifecycle
  (`deposit_session`, `collection`) and `status` everywhere else. Both are `varchar(16)` with a
  CHECK constraint that lists the allowed values. There are no PostgreSQL ENUM types.
- **Timestamps** end in `_at`. `created_at` and `updated_at` default to `now()`. No trigger keeps
  `updated_at` current: the code sets it on every change.
- **Addresses** are `varchar(42)`, lowercase `0x` hex. **Transaction hashes and sha256 digests** are
  `varchar(66)`, `0x` plus 64 hex characters. **HMACs** are `varchar(64)` hex.
- **Names written in `models.py`:**
  - `<table>_<column>_valid`: CHECK on allowed values.
  - `<table>_<column>_positive`, `bag_grams_not_negative`: CHECK on amounts.
  - `one_<thing>_per_<scope>`: unique index, usually partial.
  - `<table>_due_idx` on `(status, next_attempt_at)`: a worker's claim query.
  - `<table>_state_idx`, `<table>_status_idx`, `<table>_slot_idx`, `<table>_lookup_idx`.
- **Generated names:** `ix_<table>_<column>` (SQLAlchemy `index=True`), and PostgreSQL's defaults
  `<table>_pkey`, `<table>_<column>_key` (unique) and `<table>_<column>_fkey`.

A **partial unique index** is a unique index with a `WHERE` clause. Uniqueness applies only to rows
that match the clause. Zyrcle uses partial unique indexes to say "at most one *active* X per Y"
while it keeps finished rows.

### Identifiers that leave the database

Two ids are also ids on chain. Never change or regenerate them.

- `deposit_session.id` is the deposit's id in the Treasury: the UUID's 16 bytes, left-padded to
  `bytes32` (`deposit_id` in [`chain.py`][chain]).
- `sale_line.id` defines the on-chain sale: `keccak("zyrcle-sale-line:" + id bytes)` (`sale_id`
  in [`chain.py`][chain]).

### Retention

No job deletes old rows. The only deletes happen when an account recovery completes
(`account_recovery`, [section 3.5](#35-participants-and-accounts)). Tables such as
`device_message` (one row per device message, readings included), `session_event`, `auth_nonce`,
`email_code` and `operator_code` grow without limit.

Nothing backs up the database yet ([ADR 0020][adr-0020]).

## 2. Entity-relationship diagrams

The schema is split into three diagrams by domain. Each shows key columns only.

- A solid line is a foreign key.
- A dashed line is a logical link that code follows, without a foreign key.

### Sites, containers and deposits

```mermaid
erDiagram
    host ||--o{ site : runs
    site ||--o{ container : holds
    device ||--o| container : drives
    device ||--o{ device_message : signed
    container ||--o{ deposit_session : receives
    resident ||--o{ deposit_session : makes
    deposit_session ||--o{ session_event : "audit log"
    deposit_session ||--o| payout : "advance"
    container ||--o{ booking : "hourly spots"
    resident ||--o{ booking : holds
    material_price |o..o{ deposit_session : "declared_material (no FK)"

    host {
        uuid id PK
        string kind
        string payout_address
    }
    site {
        uuid id PK
        uuid host_id FK
        smallint opens_hour
        smallint closes_hour
        smallint slot_capacity
    }
    device {
        string id PK
        bigint last_seq
        timestamptz last_seen_at
        string current_code
    }
    container {
        string id PK
        uuid site_id FK
        string device_id FK, UK
        int area_mm2
    }
    device_message {
        string device_id PK, FK
        bigint seq PK
        string type
    }
    resident {
        uuid id PK
        string address UK
        string owner_address UK
    }
    deposit_session {
        uuid id PK
        string container_id FK
        uuid resident_id FK
        string state
        string declared_material
        int deposited_g
        uuid collection_id FK
    }
    session_event {
        bigint id PK
        uuid session_id FK
        string kind
    }
    payout {
        uuid id PK
        uuid session_id FK, UK
        int amount_cop
        string status
    }
    booking {
        uuid id PK
        uuid resident_id FK
        string container_id FK
        timestamptz starts_at
        string status
    }
    material_price {
        string material PK
        int cop_per_kg
    }
```

### Collection, sales and settlement

```mermaid
erDiagram
    resident ||--o| collector : "named collector"
    resident ||--o{ collection : "collector_id"
    container ||--o{ collection : "emptied by"
    collection ||--o{ collection_fill : has
    bag |o--o{ collection_fill : "filled by (null bag = residue)"
    resident |o--o{ bag : "collector_id"
    collection |o--o{ deposit_session : "took material of"
    container |o--o{ incident : "container_id"
    collection |o--o{ incident : "collection_id"
    incident }o..o{ bag : "bag_ids array (no FK)"
    sale ||--|{ sale_line : "one line per bag"
    bag ||--o| sale_line : "sold at most once"
    sale_line ||--o{ settlement : "settlement report"
    deposit_session ||..o{ settlement : "party_ref (no FK)"
    resident ||..o{ settlement : "party_ref (no FK)"
    host ||..o{ settlement : "party_ref (no FK)"

    collector {
        uuid resident_id PK, FK
        bool active
    }
    collection {
        uuid id PK
        string container_id FK
        uuid collector_id FK
        string state
        int expected_g
    }
    collection_fill {
        uuid id PK
        uuid collection_id FK
        uuid bag_id FK
        int start_g
        int end_g
        int grams
    }
    bag {
        uuid id PK
        string code UK
        string material
        string status
        uuid collector_id FK
        int grams
    }
    incident {
        uuid id PK
        string kind
        string status
        uuid_array bag_ids
    }
    sale {
        uuid id PK
        bigint total_cop
        string status
    }
    sale_line {
        uuid id PK
        uuid sale_id FK
        uuid bag_id FK, UK
        bigint amount_cop
        string status
    }
    settlement {
        uuid id PK
        uuid line_id FK
        string party
        string party_ref
        bigint share_cop
        bigint paid_cop
    }
```

### Accounts, notifications, email and operators

```mermaid
erDiagram
    resident ||--o{ push_token : "app installs"
    resident ||--o{ notification : "push outbox"
    resident ||--o{ email_code : "requested (ON DELETE CASCADE)"
    resident ||--o{ account_recovery : "account being recovered"
    resident |o--o{ account_recovery : "new phone (ON DELETE SET NULL)"
    operator ||..o{ operator_code : "same email (no FK)"

    resident {
        uuid id PK
        string address UK
        string owner_address UK
        string email UK
    }
    push_token {
        string token PK
        uuid resident_id FK
        timestamptz disabled_at
    }
    notification {
        uuid id PK
        uuid resident_id FK
        string dedupe_key UK
        string status
    }
    email_code {
        uuid id PK
        uuid resident_id FK
        string purpose
        string code_hash
    }
    account_recovery {
        uuid id PK
        uuid resident_id FK
        uuid new_resident_id FK
        string status
        timestamptz next_attempt_at
    }
    email_message {
        uuid id PK
        string dedupe_key UK
        string kind
        string status
    }
    auth_nonce {
        string nonce PK
        timestamptz used_at
    }
    operator {
        uuid id PK
        string email UK
        string role
    }
    operator_code {
        uuid id PK
        string email
        string code_hash
    }
```

## 3. Tables

Each table section gives its purpose, its columns, its constraints and indexes with the reason for
each, and the code that writes and reads it. Defaults are listed only when they matter. Every `id`
column is a `uuid` primary key generated by the API, unless the table says otherwise.

### 3.1 Sites, containers and devices

#### `host`

The institution that lets Zyrcle place containers on its sites: a university, a residential
complex, a business or a public body. A host receives a share of every sale of material from its
sites ([ADR 0011][adr-0011], [ADR 0013][adr-0013]).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `name` | varchar(200) | no | Display name. |
| `kind` | varchar(16) | no | `university`, `residential`, `business` or `public`. |
| `payout_address` | varchar(42) | yes | Where the host's share of each sale is paid. Null until an operator sets it. While it is null, the host's part of a sale waits. |
| `created_at` | timestamptz | no | Default `now()`. |

- `host_kind_valid`: CHECK on `kind`.

**Written by:** `create_host` in [`api.py`][api] (`POST /v1/operator/hosts`); `update_host` in
[`sale_routes.py`][sale-routes] (`PATCH /v1/operator/hosts/{id}`), which also makes waiting sale
lines retry at once when it sets an address; [`demo_seed.py`][demo-seed]; migration `0005`, which created one
`residential` host per existing residence, with the same id.
**Read by:** [`settlement.py`][settlement] (host shares), [`public.py`][public] (host dashboards),
operator routes.

#### `site`

A place a host runs, with its own containers, opening hours and turn capacity: a campus, a
building, a residential complex. It was the `residence` table until migration `0005`
([ADR 0011][adr-0011]).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. Former residences kept their id. |
| `host_id` | uuid | no | FK → `host.id`. |
| `name` | varchar(200) | no | Display name. |
| `opens_hour` | smallint | no | Default 0. First open hour, local time. |
| `closes_hour` | smallint | no | Default 24. Closing hour, not included. The site is open in `[opens_hour, closes_hour)`. |
| `slot_capacity` | smallint | no | Default 20. Participants per container per hour ([ADR 0009][adr-0009]). |
| `created_at` | timestamptz | no | |

- `site_hours_valid`: `0 <= opens_hour AND opens_hour < closes_hour AND closes_hour <= 24`. The
  booking code assumes a non-empty window inside one day.
- `site_slot_capacity_positive`: `slot_capacity > 0`. A capacity of 0 would make every hour full.
- `ix_site_host_id`.

**Written by:** `create_site` and `set_schedule` in [`api.py`][api]; [`demo_seed.py`][demo-seed].
**Read by:** [`bookings.py`][bookings] (hours and capacity), [`settlement.py`][settlement] (which
host a bag's material came from), [`public.py`][public].

#### `device`

The electronics of one container: its public key, the last sequence number it sent, and the
rotating access code it shows as a QR ([ADR 0005][adr-0005], [device protocol][device-protocol]).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | varchar(64) | no | Primary key, chosen by the operator (pattern `^[a-z0-9-]{3,64}$`, for example `ctr-0001`). |
| `public_key_pem` | text | no | ECDSA public key that verifies the device's signed messages. Public, not a secret. |
| `last_seq` | bigint | no | Default −1. Highest `seq` accepted. A message with `seq <= last_seq` is dropped. |
| `last_seen_at` | timestamptz | yes | When the last accepted message arrived. The device counts as online for `device_offline_after_s` (default 90 s) after it. |
| `firmware` | varchar(64) | yes | From the `hello` message. |
| `current_code` | varchar(16) | yes | Access code on the display now: 6 Crockford base32 characters. |
| `code_expires_at` | timestamptz | yes | End of validity of `current_code`: 2 × `code_rotation_s` after it was issued (default 60 s). |
| `previous_code` | varchar(16) | yes | The code before the last rotation. It stays valid until it expires, so a participant who scanned it a second before the screen changed is not rejected. |
| `previous_code_expires_at` | timestamptz | yes | End of validity of `previous_code`. |
| `created_at` | timestamptz | no | |

**Written by:** `register_device` in [`api.py`][api]; `handle_device_message` in
[`sessions.py`][sessions] (`last_seq`, `last_seen_at`, `firmware`), under a row lock, so messages
from one device are applied one at a time; `rotate_codes` in [`sessions.py`][sessions], every few
seconds, with `SKIP LOCKED`; [`demo_seed.py`][demo-seed].
**Read by:** deposit and collection start (`code_valid` and the online check),
[`public.py`][public] (online status), [`demo.py`][demo].

#### `container`

A physical bin on a site, driven by one device.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | varchar(64) | no | Primary key, chosen by the operator (same pattern as device ids). |
| `site_id` | uuid | no | FK → `site.id`. |
| `device_id` | varchar(64) | no | FK → `device.id`. Unique. |
| `name` | varchar(200) | no | Display name. |
| `accepted_materials` | varchar(32)[] | no | Material codes the container takes: a subset of `pet`, `hdpe`, `paper`, `cardboard`, `glass`, `metal`. The API checks the codes; the database does not. |
| `area_mm2` | integer | no | Inner cross-section. It turns a change in fill distance into a volume: `ml = Δmm × area_mm2 / 1000`. |
| `depth_mm` | integer | no | Inner depth. [`public.py`][public] divides by it to show a fill percentage. |
| `created_at` | timestamptz | no | |

- `container_device_id_key` (unique): one device drives at most one container, so a device
  message identifies its container.
- `ix_container_site_id`.
- `container_area_mm2_check` (`area_mm2 > 0`) and `container_depth_mm_check` (`depth_mm > 0`),
  since migration `0009`.

**Locking.** The container row is the lock for everything that takes a container: starting a
deposit, starting a collection, and booking or claiming a turn. Each one locks the row with
`SELECT … FOR UPDATE` before it checks anything.

**Written by:** `create_container` in [`api.py`][api]; [`demo_seed.py`][demo-seed].
**Read by:** nearly every module.

#### `device_message`

Every verified message a device sent, stored as signed. The key is `(device_id, seq)`.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `device_id` | varchar(64) | no | Part of the primary key. FK → `device.id`. |
| `seq` | bigint | no | Part of the primary key. Strictly increasing per device, kept across reboots. |
| `type` | varchar(16) | no | Envelope type, for example `hello`, `event`, `reading`, `measurement`. |
| `device_ts` | bigint | no | Device clock, unix milliseconds. Informational: the backend uses its own clock. |
| `received_at` | timestamptz | no | Default `now()`. |
| `body` | jsonb | no | The message body. |

- Primary key `(device_id, seq)`: a replayed message, or one MQTT redelivers (QoS 1), carries a
  `seq` that is already stored. `handle_device_message` drops it first, because `seq <= last_seq`
  under the device row lock. The primary key is the backstop.

**Written by:** `handle_device_message` in [`sessions.py`][sessions], in the same transaction that
applies the message. Messages that fail the signature or topic checks are never stored.

### 3.2 Deposits, turns and advances

#### `deposit_session`

One participant's use of one container, from the scan to the verdict. It holds the measurements,
the verification result and the operator's review ([architecture, sections 5 and 6][architecture]).

Two terms used below:

- The **tare** is the scale reading just before material goes in.
- A deposit is **credited** when its state is `verified` or `approved`. Its grams count, and it
  earns an advance.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. Also the deposit's id on chain ([section 1](#identifiers-that-leave-the-database)). |
| `container_id` | varchar(64) | no | FK → `container.id`. |
| `resident_id` | uuid | no | FK → `resident.id`: the participant. |
| `state` | varchar(16) | no | See [section 4.1](#41-deposit_sessionstate). |
| `declared_material` | varchar(32) | no | The material the participant declared. The code requires it to be in the container's `accepted_materials`. |
| `created_at` | timestamptz | no | When the session was authorized. |
| `updated_at` | timestamptz | no | Set by code on every transition. The measurement timeout counts from it. |
| `last_activity_at` | timestamptz | no | Last time the scale moved by at least `weight_change_g` (default 10 g). The idle timeout counts from it. |
| `close_reason` | varchar(32) | yes | `resident_finished` or `idle`. Null for other endings. The first value written stays. |
| `tare_g` | integer | yes | Scale reading when the lid opened. The final measurement overwrites it with the device's own tare. |
| `last_weight_g` | integer | yes | Last reading that moved by at least `weight_change_g`. |
| `final_g` | integer | yes | Reading after the lid closed. |
| `fill_before_mm` | integer | yes | Distance from the sensor down to the contents, before. It shrinks as the container fills. |
| `fill_after_mm` | integer | yes | The same distance, after. |
| `metal_detected` | boolean | yes | Inductive sensor result. |
| `camera_label` | varchar(32) | yes | What the camera saw. |
| `added_volume_ml` | integer | yes | `max(fill_before_mm − fill_after_mm, 0) × area_mm2 / 1000`. |
| `deposited_g` | integer | yes | Grams credited by the verification rules ([`domain/verification.py`][verification]). |
| `score` | float | yes | Confidence from 0 to 1, rounded to 3 decimals. |
| `reasons` | jsonb | yes | List of strings that explain a low score. |
| `reviewed_by` | varchar(254) | yes | The reviewing operator's email, or `token` for the shared operator token. |
| `review_note` | text | yes | The operator's note. It is shown to the participant on rejection. |
| `collection_id` | uuid | yes | FK → `collection.id`: the collection that took this deposit's material out ([ADR 0012][adr-0012]). Set when that collection closes. |

- `deposit_session_state_valid`: CHECK on `state`.
- `one_active_session_per_container`: unique `(container_id)` where `state IN ('authorized',
  'closing', 'depositing', 'open')`. A container serves one session at a time. Two participants
  who scan at the same moment can both pass the checks in `SessionService.start`. The second
  `INSERT` then fails with a unique violation, and the API answers 409 ("container is busy").
  `models.py` builds the predicate from `ACTIVE` in [`domain/session_machine.py`][machine];
  migration `0001` has the same list written out. Changing `ACTIVE` needs a migration.
- `deposit_session_state_idx` on `state`: the sweeper and the review queue select by state.
- `ix_deposit_session_collection_id`: settlement finds the deposits of a collection.
- There is no index on `resident_id`, and none on `container_id` outside the partial index.

**Written by:** [`sessions.py`][sessions] (`start`, `finish`, `review`, device messages, `sweep`);
`on_measurement` in [`collection.py`][collection] (`collection_id`); `_complete` in
[`recovery.py`][recovery] (moves rows from the new phone's resident to the recovered account).
**Read by:** [`api.py`][api] (`/v1/me`), [`public.py`][public], [`collection.py`][collection],
[`settlement.py`][settlement], [`notifications.py`][notifications].

#### `session_event`

Append-only audit log of everything that happened to a deposit session.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | bigint | no | Primary key, `bigserial`. |
| `session_id` | uuid | no | FK → `deposit_session.id`. |
| `at` | timestamptz | no | Set by code. Default `now()`. |
| `kind` | varchar(32) | no | `created`; a state-machine event such as `lock_opened` or `measured_ok`; `device:<name>` for other device events; `device:late_measurement`; `device:bad_measurement`; `advance_queued`; `no_advance`. |
| `from_state` | varchar(16) | yes | Set on transitions only. |
| `to_state` | varchar(16) | yes | Set on transitions only. |
| `data` | jsonb | yes | Payload: the device message body, the material and booking at creation, or the advance amount. |

- `ix_session_event_session_id`.

**Written by:** `_event` in [`sessions.py`][sessions] only, in the transaction of the change it
records. No code updates or deletes rows. No trigger prevents it, either.

#### `booking`

A participant's spot in one hour of one container ([ADR 0009][adr-0009]). A booked spot is
guaranteed. A participant who arrives without one gets a **walk-in** spot while the hour has room.
Walk-in spots are rows too, and they count against the capacity. One spot covers every session of
that participant at that container in that hour.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `resident_id` | uuid | no | FK → `resident.id`. |
| `container_id` | varchar(64) | no | FK → `container.id`. |
| `starts_at` | timestamptz | no | Start of a local hour (`settings.timezone`). |
| `status` | varchar(16) | no | `booked` or `cancelled`. |
| `walk_in` | boolean | no | Default false. True when the spot was taken at the container, without a booking. |
| `used_at` | timestamptz | yes | When a session first used the spot. |
| `created_at`, `updated_at` | timestamptz | no | |

- `booking_status_valid`: CHECK on `status`.
- `one_booking_per_resident_slot`: unique `(resident_id, container_id, starts_at)` where
  `status = 'booked'`. It keeps one live spot per participant, container and hour, even under
  concurrent requests. Cancelled rows fall outside the index, so a participant can book the same
  hour again after cancelling.
- `booking_slot_idx` on `(container_id, starts_at)`: counting the spots taken in an hour.
- `ix_booking_resident_id`.
- Capacity is not in the schema. The code counts booked rows under the container row lock and
  refuses when the count reaches `site.slot_capacity`.

**Written by:** [`bookings.py`][bookings] (`book`, `cancel`, and `claim_spot`, which
`SessionService.start` calls); `_complete` in [`recovery.py`][recovery].
**Read by:** [`bookings.py`][bookings]; `has_activity` in [`recovery.py`][recovery].

#### `material_price`

Reference price per material, used to size advances.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `material` | varchar(32) | no | Primary key: a material code. |
| `cop_per_kg` | integer | no | Price in COP per kilogram. |
| `source` | varchar(16) | no | Where the price came from. The code only writes `manual`. |
| `updated_at` | timestamptz | no | Default `now()`. Set by code on change. |

- `material_price_cop_per_kg_check` (`cop_per_kg >= 0`), since migration `0009`. The API also caps
  it at 1,000,000.
- The advance is `min(deposited_g × cop_per_kg × advance_ratio_bps / 10,000,000,
  max_advance_cop)`, rounded down ([`pricing.py`][pricing]). The defaults are 5,000 bps (50 %) and
  5,000 COP. A material without a row earns no advance, and the session logs `no_advance`.

**Written by:** `set_price` in [`api.py`][api] (`PUT /v1/operator/prices/{material}`);
[`demo_seed.py`][demo-seed].
**Read by:** `_queue_advance` in [`sessions.py`][sessions]; `list_prices` in [`api.py`][api].

#### `payout`

The outbox for advances. An **advance** is the payment a participant gets when a deposit is
credited, before its material is sold ([ADR 0003][adr-0003], [ADR 0007][adr-0007]). An **outbox**
is a table that a business transaction writes to, in the same database transaction, to record work
that must happen outside the database. Here the work is a Treasury transaction. If the business
transaction rolls back, the outbox row disappears with it. If it commits, the row is there for a
worker, even after a crash. See [section 5](#5-outbox-tables-and-workers).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `session_id` | uuid | no | FK → `deposit_session.id`. Unique. |
| `kind` | varchar(16) | no | Always `advance`. Settlements live in `settlement`. |
| `resident_address` | varchar(42) | no | `resident.address` when the row was written: where the ZYR goes. |
| `amount_cop` | integer | no | The advance. |
| `status` | varchar(16) | no | See [section 4.5](#45-payoutstatus). |
| `attempts` | integer | no | Default 0. Incremented on every claim. |
| `tx_hash` | varchar(66) | yes | The `payAdvance` transaction. Null when the advance was already on chain. |
| `last_error` | text | yes | Last error. |
| `next_attempt_at` | timestamptz | yes | Not due before this. Null means due now. |
| `created_at`, `updated_at` | timestamptz | no | `updated_at` also times how long a row has been `submitting`. |

- `payout_session_id_key` (unique): exactly one advance per deposit.
- `payout_status_valid`, `payout_amount_positive` (`amount_cop > 0`).
- `payout_due_idx` on `(status, next_attempt_at)`: the worker's claim query.

**Written by:** `_queue_advance` in [`sessions.py`][sessions], in the transaction that credits the
deposit; `PayoutWorker` in [`payouts.py`][payouts].
**Read by:** [`api.py`][api] (`/v1/me`); [`public.py`][public] (totals; a confirmed payout's
`updated_at` is its payment day); [`settlement.py`][settlement] (a sale line waits while an advance
for one of its deposits is `pending` or `submitting`).

### 3.3 Collection

Collection is described in [ADR 0012][adr-0012]. A collector empties a container into bags. The
container's own scale weighs every bag, so nobody declares a weight.

#### `collector`

Marks a participant as a collector. A collector is paid at the same account as any participant.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `resident_id` | uuid | no | Primary key. FK → `resident.id`. |
| `name` | varchar(200) | no | Name shown to operators. |
| `active` | boolean | no | Default true. Inactive collectors cannot start collections. |
| `created_at` | timestamptz | no | |

- `bag.collector_id` and `collection.collector_id` point to `resident.id`, not to this table. The
  schema does not require a `collector` row for them; `_require_collector` in
  [`collection.py`][collection] checks it.

**Written by:** `name_collector` in [`collection_routes.py`][collection-routes] (insert or update,
found by account address or phone key).
**Read by:** [`collection.py`][collection], [`api.py`][api] (`/v1/me`), operator listings.

#### `bag`

A bag with a printed QR, holding one material.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `code` | varchar(16) | no | Unique. 8 Crockford base32 characters (no I, L, O or U). The QR is `zyrcle://b/<code>`. |
| `material` | varchar(32) | no | The one material this bag holds. |
| `status` | varchar(16) | no | See [section 4.3](#43-bagstatus). |
| `collector_id` | uuid | yes | FK → `resident.id`. Set by the first fill. Nobody else can fill the bag after that. |
| `grams` | integer | no | Default 0. Sum of the grams of its fills, added when each fill closes. |
| `created_at` | timestamptz | no | |
| `sealed_at` | timestamptz | yes | When the collector sealed it. |

- `bag_code_key` (unique): a scanned code identifies one bag. `create_bags` retries a batch up to
  3 times if a random code collides.
- `bag_status_valid`, `bag_grams_not_negative` (`grams >= 0`).
- `ix_bag_collector_id`.

**Written by:** `create_bags` in [`collection_routes.py`][collection-routes] and
[`demo_seed.py`][demo-seed] (status `open`); `add_fill` (collector), `_close_fill` (grams) and
`seal_bag` (sealed) in [`collection.py`][collection]; `record_sale` in [`sale_routes.py`][sale-routes]
(sold); `_settle` in [`settlement.py`][settlement] (settled).
**Read by:** [`settlement.py`][settlement], [`sale_routes.py`][sale-routes], [`demo.py`][demo].

#### `collection`

A collector emptying one container into bags. To the container, a collection is one more session
id: its `id` travels in the `unlock` and `lock` commands.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. Also the session id sent to the device. |
| `container_id` | varchar(64) | no | FK → `container.id`. |
| `collector_id` | uuid | no | FK → `resident.id`. |
| `state` | varchar(16) | no | See [section 4.2](#42-collectionstate). |
| `tare_g` | integer | yes | Reading when the lid opened. The final measurement overwrites it with the device's tare. |
| `last_weight_g` | integer | yes | Latest reading. Each fill starts and ends at it. |
| `final_g` | integer | yes | Reading after the lid closed. |
| `expected_g` | integer | yes | What the container should weigh when it opens: the previous closed collection's `final_g`, plus `final_g − tare_g` of every deposit since. For a container never collected, the start is its first deposit's tare. Null when there is nothing to compare with. |
| `created_at`, `updated_at` | timestamptz | no | The measurement timeout counts from `updated_at`. |
| `last_activity_at` | timestamptz | no | Last time the scale moved by at least `weight_change_g`. The idle timeout (default 10 minutes) counts from it. |
| `closed_at` | timestamptz | yes | When the final measurement arrived. |

- `collection_state_valid`: CHECK on `state`.
- `one_active_collection_per_container`: unique `(container_id)` where `state IN ('authorized',
  'open', 'closing')`. One collector empties a container at a time. A concurrent second start
  fails the `INSERT` and gets 409.
- `collection_state_idx` on `state`: the sweeper selects by state.
- `ix_collection_container_id`, `ix_collection_collector_id`.
- A deposit and a collection must never be active on the same container at once. No index can
  span two tables, so both start paths lock the container row and check the other table.

**Written by:** [`collection.py`][collection] only.
**Read by:** `SessionService.start` (refuses while a collection is active),
[`settlement.py`][settlement] (which host a fill's material came from),
[`collection_routes.py`][collection-routes], [`demo.py`][demo].

#### `collection_fill`

One material taken out of the container during a collection. It goes into a bag, or out as
**residue**: material that is not recyclable, weighed the same way but put in no bag.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `collection_id` | uuid | no | FK → `collection.id`. |
| `bag_id` | uuid | yes | FK → `bag.id`. Null for residue. |
| `material` | varchar(32) | yes | The bag's material. Null for residue. |
| `start_g` | integer | no | `collection.last_weight_g` when the fill started. |
| `end_g` | integer | yes | The reading when the collector tapped "done". Null while the fill is open. |
| `grams` | integer | yes | `start_g − end_g`, or 0 when that difference is below `weight_change_g` (default 10 g). Set when the fill closes. |
| `started_at` | timestamptz | no | Default `now()`. |
| `done_at` | timestamptz | yes | When the fill closed. |

- `one_open_fill_per_collection`: unique `(collection_id)` where `end_g IS NULL`. One material at
  a time. A fill's grams are the difference of two readings, so two open fills would share
  readings and count the same grams twice.
- `ix_collection_fill_collection_id`, `ix_collection_fill_bag_id`.
- The code also enforces, in `add_fill`: the bag is `open`; it belongs to no other collector; the
  container accepts its material; and each material goes into a single bag per collection
  ([ADR 0013][adr-0013]).

**Written by:** `add_fill` and `_close_fill` in [`collection.py`][collection]. `_close_fill` runs
from `finish_fill`, `finish` and the idle sweep.
**Read by:** [`settlement.py`][settlement] (a bag's fills lead to its collections, deposits and
hosts); collection views.

#### `incident`

A **mass balance** that did not hold. A mass balance compares two weights that should be equal. The
tolerance is the larger of 50 g and 2 % for the container and collection balances, and the larger
of 100 g and 5 % for the bag balance. Bags named in an open incident cannot be sold, and their sale
lines do not settle.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `kind` | varchar(32) | no | `container_balance`, `collection_balance` or `bag_balance`. |
| `status` | varchar(16) | no | `open` or `resolved`. |
| `container_id` | varchar(64) | yes | FK → `container.id`. Null for `bag_balance`. |
| `collection_id` | uuid | yes | FK → `collection.id`. Null for `bag_balance`. |
| `bag_ids` | uuid[] | no | Default `'{}'`. The bags this incident blocks. No foreign key: PostgreSQL cannot put one on array elements. |
| `expected_g` | integer | no | The weight that was expected. |
| `measured_g` | integer | no | The weight that was measured. |
| `detail` | jsonb | yes | `{"tolerance_g": n}`. A `bag_balance` also has `sale_id` and `bag_code`. |
| `created_at` | timestamptz | no | |
| `resolved_at` | timestamptz | yes | |
| `resolved_by` | varchar(254) | yes | The operator's email, or `token`. |
| `resolution_note` | text | yes | Required to resolve. |

Who opens each kind:

- `container_balance`: `on_event` in [`collection.py`][collection], when the lid opens and the
  weight differs from `expected_g`. Its `bag_ids` are filled in when the collection closes.
- `collection_balance`: `on_measurement` in [`collection.py`][collection], when what left the
  container (`tare_g − final_g`) differs from the sum of the fills' grams.
- `bag_balance`: `record_sale` in [`sale_routes.py`][sale-routes], when the buyer's weight differs
  from `bag.grams`.

Constraints and indexes:

- `incident_kind_valid`, `incident_status_valid`.
- `incident_status_idx` on `status`: every sale and every settlement attempt looks for open
  incidents.

**Written by:** the three places above; `resolve_incident` in
[`collection_routes.py`][collection-routes], which also makes waiting sale lines of those bags
retry at once.

### 3.4 Sales and settlement

Sales and settlement are described in [ADR 0013][adr-0013]. A **settlement** is the payment after
a bag is sold: each credited deposit's pro-rata share of the sale, minus the advance it already got.
The collector and the hosts get their parts in the same process.

#### `sale`

A buyer's ticket for one or more bags. Nothing goes on chain until the sale is `confirmed`, which
means an operator saw the money in the bank.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `buyer` | varchar(200) | no | Who bought the material. |
| `ticket_ref` | varchar(100) | no | The ticket's reference. Not unique. |
| `sold_on` | timestamptz | no | Noon, local time, of the date the operator entered. |
| `total_cop` | bigint | no | The sum of the line amounts, computed by the code. |
| `evidence_hash` | varchar(66) | no | `0x` + sha256 of the ticket's canonical JSON (buyer, reference, date, and each line's bag code, weight and amount). Every on-chain sale carries it. |
| `status` | varchar(16) | no | `recorded` or `confirmed`. |
| `recorded_by` | varchar(254) | no | The operator's email, or `token`. |
| `bank_ref` | varchar(100) | yes | The bank transfer reference. |
| `confirmed_by` | varchar(254) | yes | The operator who confirmed the bank match. |
| `confirmed_at` | timestamptz | yes | |
| `created_at` | timestamptz | no | |

- `sale_status_valid`, `sale_total_positive` (`total_cop > 0`).

**Written by:** `record_sale` and `confirm_sale` in [`sale_routes.py`][sale-routes].
`confirm_sale` requires the amount the bank received to equal `total_cop`.
**Read by:** [`settlement.py`][settlement] (only lines of confirmed sales are claimed; the evidence
hash goes on chain).

#### `sale_line`

One bag of a sale. Each line is settled on chain as a sale of its own. The table is also the
settlement worker's queue (see [section 5](#5-outbox-tables-and-workers)).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. Defines the on-chain sale id ([section 1](#identifiers-that-leave-the-database)). |
| `sale_id` | uuid | no | FK → `sale.id`. |
| `bag_id` | uuid | no | FK → `bag.id`. Unique. |
| `buyer_g` | integer | no | The buyer's weight for this bag. |
| `amount_cop` | bigint | no | Pesos paid for this bag. |
| `status` | varchar(16) | no | See [section 4.4](#44-salestatus-and-sale_linestatus). |
| `reason` | text | yes | Why the line is waiting, or why it failed. |
| `attempts` | integer | no | Default 0. Incremented on every claim. |
| `next_attempt_at` | timestamptz | yes | Not due before this. Null means due now. |
| `residents_cop` | bigint | yes | Sum of the deposits' shares, once computed. |
| `collector_cop` | bigint | yes | The collector's share, once computed. |
| `host_cop` | bigint | yes | Sum of the shares of hosts that have a payout address. |
| `txs` | jsonb | no | Default `'[]'`. The transactions sent, in order: `{"step", "tx", "at"}`. |
| `report_hash` | varchar(66) | yes | `0x` + sha256 of the settlement report's canonical JSON, anchored on chain with the payments. |
| `settled_at` | timestamptz | yes | When every part was paid. |
| `created_at`, `updated_at` | timestamptz | no | `updated_at` also times how long a line has been `settling`. |

- `sale_line_bag_id_key` (unique): a bag is sold at most once, ever.
- `sale_line_status_valid`, `sale_line_amount_positive` (`amount_cop > 0`),
  `sale_line_buyer_g_positive` (`buyer_g > 0`).
- `sale_line_due_idx` on `(status, next_attempt_at)`: the worker's claim query.
- `ix_sale_line_sale_id`.

**Written by:** `record_sale` in [`sale_routes.py`][sale-routes] (inserts `pending` lines);
`SettlementWorker` in [`settlement.py`][settlement]; `resolve_incident` in
[`collection_routes.py`][collection-routes] and `update_host` in [`sale_routes.py`][sale-routes],
which set `next_attempt_at = now()` on waiting lines.
**Read by:** [`sale_routes.py`][sale-routes].

#### `settlement`

The published settlement report: what one party got from one sale line.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `line_id` | uuid | no | FK → `sale_line.id`. |
| `party` | varchar(16) | no | `deposit`, `collector` or `host`. |
| `party_ref` | varchar(64) | no | The deposit session id, the collector's resident id or the host id, as text. No foreign key. |
| `address` | varchar(42) | yes | Where the part was paid. Null for a host without a payout address. |
| `grams` | integer | no | The deposit's `deposited_g`; the bag's grams for the collector; the grams from the host's sites. |
| `share_cop` | bigint | no | The party's pro-rata part, rounded down to whole pesos. |
| `paid_cop` | bigint | yes | For a deposit: `max(share − advance, 0)`, with the advance read from the chain. For others: the share. Null until paid. |
| `tx_hash` | varchar(66) | yes | The transaction that paid it. Null when an earlier attempt paid it but its bookkeeping was lost, or when nothing was owed. |
| `created_at` | timestamptz | no | |

- `one_settlement_per_party`: unique `(line_id, party, party_ref)`. It is the conflict target of
  the upsert in `_save_shares`, so a retry updates the rows instead of duplicating them.
- `settlement_party_valid`.
- `ix_settlement_line_id`.

**Written by:** [`settlement.py`][settlement]: `_save_shares` inserts or updates the shares;
`_mark` writes `paid_cop` and `tx_hash` once, only while `paid_cop` is null.
**Read by:** `get_sale` in [`sale_routes.py`][sale-routes]; [`api.py`][api] (`/v1/me` shows what
each deposit got); `notify_settlement` in [`notifications.py`][notifications].

### 3.4b Impact certificates

[ADR 0027](adr/0027-impact-certificates.md). Written by [`impact.py`](../apps/api/src/zyrcle_api/impact.py).

**`certificate`.** A host's (or one site's) certificate for a month.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key; its 16 bytes go into the anchor transaction. |
| `host_id` | uuid | no | FK → `host.id`. |
| `site_id` | uuid | yes | FK → `site.id`; null for the whole host. |
| `period` | varchar(7) | no | `YYYY-MM`, local time. CHECK `certificate_period_valid`. |
| `factors_version` | varchar(16) | no | Emission factor table used, `warm-v16`. |
| `deposits`, `participants` | integer | no | How many deposits and distinct participants it covers. |
| `grams`, `co2e_g` | bigint | no | Material sold, and grams of CO2e avoided against landfilling. |
| `by_material` | jsonb | no | `{material: {"grams", "co2e_g"}}`. |
| `merkle_root` | varchar(66) | no | `0x` + sha256 root of the leaves. |
| `status` | varchar(16) | no | `issued`, `anchored`, `failed`. |
| `anchor_tx` | varchar(66) | yes | The transaction whose data carries the root. |
| `attempts`, `next_attempt_at`, `last_error` | | | Anchor worker bookkeeping. |
| `issued_by` | varchar(254) | no | The operator's email, or `token`. |
| `created_at`, `anchored_at` | timestamptz | | |

Indexes: `certificate_host_period_idx`, `certificate_due_idx` (anchor worker).

**`impact_claim`.** The claim ledger: one environmental attribute of one deposit, claimed once.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `session_id` | uuid | no | FK → `deposit_session.id`. |
| `attribute` | varchar(16) | no | `co2e` (CHECK `impact_claim_attribute_valid`). |
| `certificate_id` | uuid | no | FK → `certificate.id`. |
| `grams` | integer | no | The deposit's verified grams at the time of the claim. |
| `created_at` | timestamptz | no | |

`one_claim_per_deposit_attribute` (unique `session_id, attribute`) is what makes "one gram, one
claim" a database rule: a second certificate over the same deposit fails on it, even under
concurrent requests.

### 3.5 Participants and accounts

#### `resident`

A participant's account. The table name is older than collectors and hosts; it holds every
participant, collectors included. A participant is their account, not their phone
([ADR 0010][adr-0010]).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `address` | varchar(42) | no | Unique. Where the participant's ZYR lives: their smart account, at the address the account factory predicts for their first phone key. It does not change once set. It equals `owner_address` when smart accounts are not configured, and for residents created before them until their next sign-in. |
| `owner_address` | varchar(42) | no | Unique. The phone key that signs in and controls the account. A recovery replaces it. |
| `email` | varchar(254) | yes | Unique. The verified recovery email, lowercase. Set only after the participant typed the code sent to it. |
| `email_verified_at` | timestamptz | yes | |
| `created_at` | timestamptz | no | |

- `resident_owner_address_key` (unique): sign-in finds the resident by the signing key.
- `resident_address_key` (unique): one resident per account. A key whose account moved to another
  phone would get the same predicted address, so sign-in refuses it (`key_retired`).
- `resident_email_key` (unique): an email identifies exactly one account for recovery.

**Written by:** `verify_siwe` in [`auth.py`][auth] (creates a resident on a key's first sign-in;
gives older residents their account address); `verify_email` and `ensure_account` in
[`recovery.py`][recovery]; `_complete` in [`recovery.py`][recovery] (sets the new
`owner_address` and deletes the new phone's own resident).
**Read by:** almost everything. `resident_dep` in [`api.py`][api] checks `owner_address` against
the token on every request, so a recovery ends the old phone's session at once.

#### `auth_nonce`

Single-use nonces for Sign-In with Ethereum (EIP-4361). A **nonce** is a random value that a
signed message may use only once.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `nonce` | varchar(64) | no | Primary key: 32 random hex characters. |
| `expires_at` | timestamptz | no | 5 minutes after it was issued. |
| `used_at` | timestamptz | yes | When a sign-in used it. |

- The nonce is burned atomically: `UPDATE … SET used_at = now WHERE nonce = :n AND used_at IS NULL
  AND expires_at > now`. Exactly one row must change. A replayed sign-in message fails here.

**Written by:** `new_nonce` and `verify_siwe` in [`auth.py`][auth]. No code deletes old rows.

#### `email_code`

A six-digit code sent by email, to verify a recovery email (`verify`) or to recover an account
(`recover`). Only an HMAC of the code is stored. An **HMAC** is a hash computed with a secret key.
Without the key, a leaked digest cannot be checked against the million possible codes.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `purpose` | varchar(16) | no | `verify` or `recover`. |
| `email` | varchar(254) | no | The address, lowercase. It may belong to no account. |
| `resident_id` | uuid | no | FK → `resident.id`, `ON DELETE CASCADE`: the resident who asked. |
| `code_hash` | varchar(64) | no | HMAC-SHA256, hex, keyed with `settings.jwt_secret`, over `purpose\|email\|requester id\|code`. A code is useless for another purpose, address or phone. |
| `attempts` | integer | no | Default 0. Wrong guesses. |
| `expires_at` | timestamptz | no | 10 minutes after it was issued. |
| `used_at` | timestamptz | yes | Set when the code is consumed, replaced by a newer one, or burned by the fifth wrong guess. |
| `created_at` | timestamptz | no | |

- `email_code_purpose_valid`.
- `email_code_lookup_idx` on `(email, purpose, created_at)`: the rate limits (one code per minute
  and five per day per address and purpose) and the lookup of the latest code.
- `ix_email_code_resident_id`: the limit of ten codes per day per requester.
- `ON DELETE CASCADE`: a recovery deletes the new phone's resident when it completes, and its codes
  go with it.
- A code row is created even for an address with no account. No email is sent then, but the answer
  and the rate limits are the same, so nobody can probe which addresses have accounts.

**Written by:** `issue_code` and `check_code` in [`recovery.py`][recovery]. Wrong guesses are
committed even though the request then fails.

#### `account_recovery`

Moving an account to a new phone key ([ADR 0010][adr-0010]). The new phone signs in as an empty
resident of its own (`new_resident_id`). When the recovery completes, that resident is folded into
the account. The table is also the recovery worker's queue.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `resident_id` | uuid | no | FK → `resident.id`: the account being recovered. |
| `new_resident_id` | uuid | yes | FK → `resident.id`, `ON DELETE SET NULL`: the new phone's own resident. Cleared when it is folded in. |
| `account_address` | varchar(42) | no | The account's address. |
| `new_owner` | varchar(42) | no | The new phone's key. |
| `status` | varchar(16) | no | See [section 4.8](#48-account_recoverystatus). |
| `ready_at` | timestamptz | no | When the chain lets `finishRecovery` run. First an estimate (now + 48 hours), then the chain's own `readyAt`. |
| `cancelled_by` | varchar(16) | yes | `owner`, `new_phone`, `chain` or `replaced`. |
| `start_tx`, `finish_tx`, `cancel_tx` | varchar(66) | yes | The guardian's transactions. Null when a step needed no transaction. |
| `attempts` | integer | no | Default 0. Incremented on every claim. |
| `next_attempt_at` | timestamptz | no | When the worker next looks at the row. While a worker holds the row, it is set 2 minutes ahead as a lease. |
| `last_error` | text | yes | |
| `created_at`, `updated_at` | timestamptz | no | |

A **lease** is a time during which a claimed row is left alone by other workers.

- `account_recovery_status_valid`.
- `one_live_recovery_per_account`: unique `(resident_id)` where `status IN ('starting', 'waiting',
  'cancelling')`. An account has one pending recovery on chain at a time. A newer verified request
  first marks the live one `cancelled` (`cancelled_by = 'replaced'`), then inserts.
- `one_live_recovery_per_new_phone`: unique `(new_resident_id)` with the same condition. A phone
  recovers one account at a time. PostgreSQL treats NULLs as distinct in a unique index, but the
  code clears `new_resident_id` only when a recovery is done.
- `account_recovery_due_idx` on `(status, next_attempt_at)`: the worker's claim query.
- `ix_account_recovery_resident_id`.

**Written by:** [`recovery.py`][recovery]: `start_recovery`, `cancel_recovery` and
`RecoveryWorker`.
**What a completed recovery changes,** in one transaction (`_complete`): it deletes the account's
old push tokens; moves the new phone's push tokens, deposit sessions and bookings to the account;
deletes the new phone's notifications; deletes the new phone's resident (its `email_code` rows
cascade); and sets `resident.owner_address` to the new key.

### 3.6 Push and email

#### `push_token`

An Expo push token: one per installed app ([ADR 0008][adr-0008]).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `token` | varchar(200) | no | Primary key, for example `ExponentPushToken[…]`. |
| `resident_id` | uuid | no | FK → `resident.id`: the wallet now on that phone. |
| `platform` | varchar(16) | no | `ios` or `android` (checked by the API). |
| `created_at`, `updated_at` | timestamptz | no | |
| `disabled_at` | timestamptz | yes | Set when Expo reports `DeviceNotRegistered` (the app was uninstalled). Registering again clears it. |

- `ix_push_token_resident_id`.
- Registration is an upsert on `token`. A token registered by another wallet moves to the caller,
  because only the wallet now on that phone should get notifications.

**Written by:** `register_push_token` in [`api.py`][api] (`PUT /v1/me/push-token`);
`NotificationWorker` in [`notifications.py`][notifications] (`disabled_at`);
`_complete` in [`recovery.py`][recovery].

#### `notification`

The outbox for push notifications. It is written in the transaction that caused the notification
([ADR 0008][adr-0008]).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `resident_id` | uuid | no | FK → `resident.id`: who to notify. |
| `kind` | varchar(32) | no | `deposit_review`, `deposit_rejected`, `deposit_approved`, `payout_confirmed`, `settlement_paid`, `recovery_started`, `recovery_done` or `recovery_cancelled`. |
| `dedupe_key` | varchar(120) | no | Unique. `<kind>:<id of the cause>`, for example `payout_confirmed:<payout id>`. |
| `title` | varchar(120) | no | Notification title. |
| `body` | varchar(400) | no | Notification text. |
| `data` | jsonb | no | What the app opens: `url`, plus ids such as `session_id`, `tx_hash` or `recovery_id`. |
| `status` | varchar(16) | no | See [section 4.6](#46-notificationstatus). |
| `attempts` | integer | no | Default 0. Send attempts. |
| `next_attempt_at` | timestamptz | yes | Not due before this. Null means due now. |
| `tickets` | jsonb | yes | Expo tickets awaiting a receipt: `[{"token", "id"}]`. |
| `receipts_checked_at` | timestamptz | yes | When the receipts were read. |
| `last_error` | text | yes | |
| `created_at` | timestamptz | no | |
| `sent_at` | timestamptz | yes | When Expo accepted at least one message. |

- `notification_dedupe_key_key` (unique): enqueueing is `INSERT … ON CONFLICT (dedupe_key) DO
  NOTHING`, so a retried transaction never notifies twice.
- `notification_status_valid`.
- `notification_due_idx` on `(status, next_attempt_at)`: the worker's claim query.
- `ix_notification_resident_id`.

**Written by:** `enqueue` in [`notifications.py`][notifications], called from
[`sessions.py`][sessions], [`payouts.py`][payouts], [`settlement.py`][settlement] and
[`recovery.py`][recovery]; `NotificationWorker`; `_complete` in [`recovery.py`][recovery] (deletes
the new phone's rows).

#### `email_message`

The outbox for email. It is written in the transaction that caused the email and sent by a worker
through Resend's HTTP API ([ADR 0010][adr-0010]).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. Also the `Idempotency-Key` sent to Resend. |
| `kind` | varchar(32) | no | `code_verify`, `code_recover`, `code_operator`, `recovery_started`, `recovery_cancelled` or `recovery_done`. |
| `dedupe_key` | varchar(120) | no | Unique. For example `code:<email_code id>`, `code_operator:<operator_code id>` or `recovery_started:<recovery id>`. |
| `to` | varchar(254) | no | Recipient. `to` is an SQL keyword: quote it in raw SQL. |
| `subject` | varchar(200) | no | Subject. |
| `text_body` | text | no | Plain-text body. |
| `html_body` | text | no | HTML body. |
| `status` | varchar(16) | no | See [section 4.7](#47-email_messagestatus). |
| `attempts` | integer | no | Default 0. Send attempts. |
| `next_attempt_at` | timestamptz | yes | Not due before this. Set to the enqueue time, moved by retries, cleared when the row is `sent` or `failed`. |
| `provider_id` | varchar(64) | yes | Resend's email id, or `log-<id>` in log-only mode. |
| `last_error` | text | yes | |
| `created_at` | timestamptz | no | |
| `sent_at` | timestamptz | yes | |

- `email_message_dedupe_key_key` (unique): enqueueing is `INSERT … ON CONFLICT (dedupe_key) DO
  NOTHING`.
- `email_message_status_valid`.
- `email_message_due_idx` on `(status, next_attempt_at)`: the worker's claim query.
- For the three `code_*` kinds, the worker replaces the subject with "Código de Zyrcle" and empties
  both bodies when the row ends `sent` or `failed` ([section 8](#8-data-that-must-never-be-stored)).

**Written by:** `enqueue_email` in [`mail.py`][mail], called from [`recovery.py`][recovery] and
[`operator_auth.py`][operator-auth]; `EmailWorker` in [`mail.py`][mail].

### 3.7 Operators

#### `operator`

A person who runs Zyrcle from the console ([ADR 0014][adr-0014]). Operators sign in with an email
code. The shared operator token used by scripts and tests is not a row; it acts as an admin named
`token`.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `email` | varchar(254) | no | Unique, lowercase. |
| `name` | varchar(200) | no | |
| `role` | varchar(16) | no | `admin` or `operator`. Only admins manage operators. |
| `active` | boolean | no | Default true. An inactive operator's session ends on the next request. |
| `last_login_at` | timestamptz | yes | |
| `created_at` | timestamptz | no | |

- `operator_email_key` (unique), `operator_role_valid`.

**Written by:** `add_operator`, `update_operator` and `login` (`last_login_at`) in
[`operator_auth.py`][operator-auth]. Admins cannot demote or deactivate themselves.
**Read by:** `operator_who` in [`operator_auth.py`][operator-auth], on every operator request.

#### `operator_code`

A sign-in code sent to an operator's email. Codes are keyed by the address, not by the operator, so
an address that belongs to nobody is limited and answered exactly like one that does.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | uuid | no | Primary key. |
| `email` | varchar(254) | no | The address, lowercase. No foreign key. |
| `code_hash` | varchar(64) | no | HMAC-SHA256, hex, keyed with `settings.jwt_secret`, over `operator\|email\|code`. |
| `attempts` | integer | no | Default 0. Wrong guesses. |
| `expires_at` | timestamptz | no | 10 minutes after it was issued. |
| `used_at` | timestamptz | yes | Set when the code is consumed, replaced, or burned by the fifth wrong guess. |
| `created_at` | timestamptz | no | |

- `operator_code_lookup_idx` on `(email, created_at)`: the rate limits (one code per minute and
  ten per day per address) and the lookup of the latest code.

**Written by:** `request_code` and `login` in [`operator_auth.py`][operator-auth]. An email is
enqueued only for an active operator's address.

### 3.8 `alembic_version`

Alembic's own bookkeeping table. One row, `version_num varchar(32)`, holds the current revision
(`0008`).

## 4. State machines

CHECK constraints only limit the values a column may hold. Code decides which transitions are
allowed. For deposit sessions the rules live in a pure module,
[`domain/session_machine.py`][machine]. Other tables change status in the modules named below.

### 4.1 `deposit_session.state`

```mermaid
stateDiagram-v2
    [*] --> authorized : participant starts a session
    authorized --> open : lock_opened
    authorized --> expired : unlock_timeout
    open --> depositing : weight_changed
    depositing --> depositing : weight_changed
    open --> closing : finish_requested or idle_timeout
    depositing --> closing : finish_requested or idle_timeout
    closing --> verified : measured_ok
    closing --> review : measured_suspect
    closing --> empty : measured_empty
    closing --> failed : measurement_timeout
    review --> approved : approved
    review --> rejected : rejected
    verified --> [*]
    approved --> [*]
    rejected --> [*]
    empty --> [*]
    expired --> [*]
    failed --> [*]
```

| Event | What triggers it | Code |
|---|---|---|
| (create) | The participant scans the container's QR. | `SessionService.start` |
| `lock_opened` | The device reports the lid opened. Stores `tare_g` and `fill_before_mm`. | `_on_event` |
| `weight_changed` | A reading at least `weight_change_g` (10 g) away from the tare, while `open`. | `_on_reading` |
| `finish_requested` | The participant taps "done". Sets `close_reason = 'resident_finished'`. | `finish` |
| `idle_timeout` | Sweep: `last_activity_at` older than `idle_timeout_s` (60 s). Sets `close_reason = 'idle'`. | `sweep` |
| `unlock_timeout` | Sweep: `created_at` older than `unlock_ack_timeout_s` (15 s). | `sweep` |
| `measured_*` | The device's final measurement while `closing`. `verify()` decides the outcome. | `_on_measurement` |
| `measurement_timeout` | Sweep: `updated_at` older than `measurement_timeout_s` (20 s) while `closing`. | `sweep` |
| `approved`, `rejected` | An operator reviews the deposit. | `review` |

All of these live in [`sessions.py`][sessions]. The timeouts are defaults from
[`config.py`][config].

- The machine allows `depositing → depositing`, but `_on_reading` only fires `weight_changed`
  while the session is `open`.
- **Active** states (`authorized`, `open`, `depositing`, `closing`) hold the container. The
  partial unique index allows one per container.
- **Credited** states are `verified` and `approved`. Entering one writes the payout row, if the
  advance is above zero.
- `review` waits for an operator. Every other state after `closing` is terminal.
- Notifications written in the same transaction: entering `review` (`deposit_review`); `review →
  rejected` (`deposit_rejected`); `review → approved` when no advance was queued
  (`deposit_approved`). A paid advance is announced when its payout confirms.

### 4.2 `collection.state`

```mermaid
stateDiagram-v2
    [*] --> authorized : collector scans the container
    authorized --> open : device reports lock_opened
    authorized --> expired : no lock_opened within the unlock timeout
    open --> closing : collector taps finish, or 10 minutes idle
    closing --> closed : device sends the final measurement
    closing --> failed : no measurement within the measurement timeout
    closed --> [*]
    expired --> [*]
    failed --> [*]
```

- All transitions are in [`collection.py`][collection]: `start`, `on_event`, `finish`,
  `on_measurement` and `sweep`.
- Going to `closing` closes any open fill first.
- Entering `open` computes `expected_g` and may open a `container_balance` incident.
- Entering `closed` links deposits to the collection and may open a `collection_balance` incident.
  The linked deposits are those of the same container, created before the collection, not yet
  linked, in state `verified`, `approved`, `review` or `rejected`, whose material went into a bag
  in this collection.

### 4.3 `bag.status`

```mermaid
stateDiagram-v2
    [*] --> open : operator creates a batch
    open --> sealed : collector seals it
    sealed --> sold : operator records a sale
    sold --> settled : its sale line settled
    settled --> [*]
```

- `open → sealed` requires no open fill and `grams > 0` (`seal_bag` in
  [`collection.py`][collection]). Sealing twice is harmless.
- `sealed → sold` requires no open incident naming the bag (`record_sale` in
  [`sale_routes.py`][sale-routes]).
- `sold → settled` happens in `_settle` in [`settlement.py`][settlement].
- No code moves a bag backwards.

### 4.4 `sale.status` and `sale_line.status`

A sale is `recorded` when the operator enters the ticket. It becomes `confirmed` when the operator
enters the bank reference and the received amount equals `total_cop`. There is no other
transition.

```mermaid
stateDiagram-v2
    [*] --> pending : sale recorded
    pending --> settling : claimed after the sale is confirmed
    waiting --> settling : claimed when due
    settling --> settling : stuck over 2 minutes, claimed again
    settling --> settled : every part paid
    settling --> waiting : a precondition is not met, or the contract says not now
    settling --> pending : network or other error
    settling --> failed : any other contract error
    settled --> [*]
    failed --> [*]
```

- A line goes `waiting` when: an open incident names its bag; a deposit in the bag is in `review`;
  an advance for a deposit in the bag is `pending` or `submitting`; or a host with a share has no
  payout address. It retries after 30 seconds, or at once when the incident is resolved or a
  host's address is set.
- The contract errors `UnbackedMint` and `EnforcedPause` mean "not now". The line waits 10 minutes.
- No code retries a `failed` line.

### 4.5 `payout.status`

```mermaid
stateDiagram-v2
    [*] --> pending : deposit credited
    pending --> submitting : claimed
    deferred --> submitting : claimed when due
    submitting --> confirmed : paid, already on chain, or stuck and found paid
    submitting --> deferred : DailyCapExceeded, UnbackedMint or EnforcedPause
    submitting --> failed : any other contract error
    submitting --> pending : network error, or stuck and found unpaid
    confirmed --> [*]
    failed --> [*]
```

- `DailyCapExceeded` defers the payout to the next UTC midnight (plus 5 seconds). `UnbackedMint`
  and `EnforcedPause` defer it 10 minutes. A network error retries after 30 seconds.
- The contract error `AdvanceAlreadyPaid` counts as `confirmed`.
- A row "stuck" means `submitting` with `updated_at` older than 2 minutes.
- Entering `confirmed` writes a `payout_confirmed` notification in the same transaction.
- No code retries a `failed` payout.
- A settlement waits only for `pending` and `submitting` payouts, not `deferred` ones. If a deposit
  is settled first, the Treasury refuses the late advance (`DepositAlreadySettled` in
  [`Treasury.sol`][treasury]), and the payout ends `failed`.

### 4.6 `notification.status`

```mermaid
stateDiagram-v2
    [*] --> pending : enqueued
    pending --> pending : retryable error, under 6 attempts
    pending --> sent : at least one ticket accepted
    pending --> skipped : no enabled push token
    pending --> failed : request rejected, every ticket failed, or 6 attempts
    sent --> sent : receipts read, status unchanged
    sent --> [*]
    skipped --> [*]
    failed --> [*]
```

- Retryable errors are network errors, HTTP 429 and 5xx, and `MessageRateExceeded`. The wait is
  `min(15 × 2^attempts, 1800)` seconds.
- A receipt with an error writes `last_error` but keeps `sent`.

### 4.7 `email_message.status`

```mermaid
stateDiagram-v2
    [*] --> pending : enqueued
    pending --> pending : provider unavailable, under 6 attempts
    pending --> sent : provider accepted
    pending --> failed : rejected, 6 attempts, or code email older than 10 minutes
    sent --> [*]
    failed --> [*]
```

- "Provider unavailable" means a network error, HTTP 429, HTTP 5xx or
  `concurrent_idempotent_requests`. The wait is the provider's own time when it gives one (quota:
  the next UTC midnight plus one minute), otherwise `min(15 × 2^attempts, 1800)` seconds.
- Other 4xx answers mean "rejected" and fail the row.

### 4.8 `account_recovery.status`

```mermaid
stateDiagram-v2
    [*] --> starting : new phone proves the email
    starting --> waiting : startRecovery on chain
    starting --> cancelling : owner or new phone cancels
    waiting --> cancelling : owner or new phone cancels
    waiting --> done : finishRecovery after ready_at
    waiting --> cancelled : cancelled on chain by the owner, or replaced
    cancelling --> cancelled : cancelled on chain, or nothing was pending, or replaced
    cancelling --> done : the chain had already finished it
    starting --> cancelled : replaced by a newer request
    starting --> failed : contract error
    waiting --> failed : contract error
    cancelling --> failed : contract error
    done --> [*]
    cancelled --> [*]
    failed --> [*]
```

- **Live** states are `starting`, `waiting` and `cancelling`. The two partial unique indexes cover
  them.
- `cancelled_by` records who ended it: `owner`, `new_phone`, `chain` or `replaced`.
- The contract error `RecoveryNotReady` does not fail the row. The worker tries again a minute
  later, because the chain's clock may be behind the server's.
- Other errors (network) retry after 30 seconds without a status change.
- All transitions are in [`recovery.py`][recovery].

### 4.9 Other status columns

- `booking.status`: `booked → cancelled`. The participant can cancel before the hour ends, unless
  the spot is a walk-in or was already used ([`bookings.py`][bookings]).
- `incident.status`: `open → resolved`, by an operator with a note.

## 5. Outbox tables and workers

An outbox row is written in the same transaction as its cause (definition in
[section 3.2](#payout)). A worker, started in [`main.py`][main], reads due rows and does the work.
Each worker runs inside every API replica where it is configured. The outbox workers claim rows
with a query of this shape:

```sql
SELECT … WHERE status IN (…)
  AND (next_attempt_at IS NULL OR next_attempt_at <= now)
ORDER BY created_at LIMIT n
FOR UPDATE SKIP LOCKED
```

The `<table>_due_idx` index on `(status, next_attempt_at)` serves this query.

There are two claim styles:

- **Claim, commit, then work** (`payout`, `sale_line`, `account_recovery`). The worker marks the
  rows as claimed and commits before it calls the chain. No database lock is held during a slow
  chain call. If the process dies, the row stays claimed; a stuck-row rule takes it again after
  2 minutes. Every step reads the chain first, so redoing it never pays twice.
- **Lock while sending** (`notification`, `email_message`). The worker keeps the row locks for the
  whole HTTP request and commits the outcome at the end. If the process dies, the transaction rolls
  back and the rows are sent again.

| Outbox | Enqueued by | Claim | Retries | Idempotency |
|---|---|---|---|---|
| `payout` | `_queue_advance` in [`sessions.py`][sessions], when a deposit is credited. | `pending` or `deferred` and due → `submitting`, `attempts + 1`, commit. Batch of 10 every `payout_interval_s` (2 s). Stuck `submitting` rows (older than 2 minutes) are settled first by asking the chain (`advanceOf`). | Network: 30 s. Daily cap: next UTC midnight. Paused or unbacked: 10 minutes. Other contract errors: `failed`, no retry. No attempt limit. | `payout_session_id_key` allows one row per deposit. The worker checks `advanceOf` before sending. The contract refuses a second advance. |
| `sale_line` | `record_sale` in [`sale_routes.py`][sale-routes]. Not due until its sale is `confirmed`. | Lines of confirmed sales, `pending` or `waiting` and due, or `settling` with `updated_at` older than 2 minutes → `settling`, `attempts + 1`, commit. `FOR UPDATE OF sale_line SKIP LOCKED`. Batch of 5 every `settlement_interval_s` (3 s). Each transaction sent updates `updated_at`, which extends the claim. | Precondition not met: 30 s. "Not now" contract errors: 10 minutes. Network: 30 s, back to `pending`. Other contract errors: `failed`. | Before each step the worker reads the chain: sale recorded, `depositSettled`, collector and host parts already paid. Settlement rows are upserted on `one_settlement_per_party`, and `paid_cop` is written once. The contract refuses double payments. |
| `notification` | `enqueue` in [`notifications.py`][notifications]. | `pending` and due. Batch of 50 every `notification_interval_s` (2 s). Also locks the participants' enabled push tokens. Requests carry up to 100 messages. | Network, 429, 5xx, `MessageRateExceeded`: `min(15 × 2^attempts, 1800)` s, up to 6 attempts. About 15 minutes after sending, a second pass reads Expo's receipts. | `dedupe_key` makes enqueueing idempotent. Delivery is at least once: a crash after Expo accepted, before the commit, sends again. |
| `email_message` | `enqueue_email` in [`mail.py`][mail]. | `pending` and due. Batch of 10 every `email_interval_s` (1 s). | Provider unavailable: the provider's retry time or `min(15 × 2^attempts, 1800)` s, up to 6 attempts. Code emails older than 10 minutes fail unsent. | `dedupe_key` makes enqueueing idempotent. Resend receives `Idempotency-Key = email_message.id`, so a resend after a crash or a timeout does not send a second email ([`mail.py`][mail]). |

`account_recovery` follows the claim-then-work style without being a strict outbox. The worker
selects live rows with `next_attempt_at <= now` (`SKIP LOCKED`), sets `next_attempt_at` to now +
2 minutes as a lease, increments `attempts`, commits, then runs the chain step for the row's
status. Every step reads the chain first.

Two other jobs use `SKIP LOCKED` but are not outboxes: the deposit and collection sweepers (time
out stalled rows) and `rotate_codes` (new QR codes for online devices).

Workers start only when their dependencies are configured ([`main.py`][main], [`config.py`][config]):

- payouts need the chain (`chain_enabled`);
- settlements need the chain and the operator key (`sales_enabled`);
- recoveries need the chain and the account factory (`accounts_enabled`);
- email needs a Resend key or log-only mode (`email_enabled`);
- push needs `push_enabled`.

Until a worker runs, its rows stay `pending`.

## 6. Invariants: schema versus code

### Enforced by the schema

| Invariant | Mechanism |
|---|---|
| One active deposit session per container | Partial unique index `one_active_session_per_container` |
| One active collection per container | Partial unique index `one_active_collection_per_container` |
| One open fill per collection | Partial unique index `one_open_fill_per_collection` |
| One live booking per participant, container and hour | Partial unique index `one_booking_per_resident_slot` |
| One live recovery per account, and per new phone | Partial unique indexes `one_live_recovery_per_account`, `one_live_recovery_per_new_phone` |
| One advance per deposit | `payout_session_id_key` |
| A bag is sold at most once | `sale_line_bag_id_key` |
| One settlement row per party per sale line | `one_settlement_per_party` |
| A device message is stored once | Primary key `(device_id, seq)` |
| Containers have a positive area and depth; prices are not negative | `container_area_mm2_check`, `container_depth_mm_check`, `material_price_cop_per_kg_check` (migration `0009`) |
| A device drives at most one container | `container_device_id_key` |
| Unique identities | Unique `resident.address`, `resident.owner_address`, `resident.email`, `operator.email`, `bag.code` |
| Enqueueing a notification or an email is idempotent | Unique `dedupe_key` |
| Status, state, kind, role, party and purpose values | `*_valid` CHECK constraints |
| Positive amounts | `payout_amount_positive`, `sale_total_positive`, `sale_line_amount_positive`, `sale_line_buyer_g_positive`, `bag_grams_not_negative` |
| Valid opening hours and capacity | `site_hours_valid`, `site_slot_capacity_positive` |
| References exist | Foreign keys; `email_code.resident_id` cascades; `account_recovery.new_resident_id` is set null |

### Enforced only by code

| Invariant | Where | Note |
|---|---|---|
| Only allowed transitions happen | [`domain/session_machine.py`][machine] and each module | CHECKs limit values, not transitions. |
| A participant has at most one active deposit session | `SessionService.start` | A plain check. Two starts on different containers at the same instant lock different rows and are not serialised. |
| A collector has at most one active collection | `CollectionService.start` | Same caveat. |
| No deposit while a collection is active on the container, and the reverse | Both start paths | They lock the container row, then check the other table. An index cannot span two tables. |
| Slot capacity | [`bookings.py`][bookings] | Counted under the container row lock. |
| Booking rules: on the hour, up to 7 days ahead, at most 3 upcoming, cancel rules | [`bookings.py`][bookings] | |
| A new phone waiting for a recovery cannot deposit or book | `recovery_pending` in [`recovery.py`][recovery] | |
| Device `seq` strictly increases | `handle_device_message` | `last_seq` checked under the device row lock. The primary key only stops exact duplicates. |
| One bag per material per collection; the bag is open, belongs to this collector, and its material is accepted | `add_fill` in [`collection.py`][collection] | |
| `bag.grams` equals the sum of its fills' grams | `_close_fill` in [`collection.py`][collection] | |
| Only sealed bags without open incidents are sold; a weight gap opens a `bag_balance` incident | `record_sale` | |
| A sale is confirmed only when the bank amount equals `total_cop` | `confirm_sale` | |
| Nothing settles before confirmation, or while an incident, a review or an advance is pending | `SettlementWorker._claim`, `_plan` | |
| Material codes are valid | [`api.py`][api] and [`collection_routes.py`][collection-routes] (`MATERIALS`) | No CHECK on `accepted_materials`, `declared_material`, `bag.material` or `material_price.material`. |
| Addresses and emails are lowercase | [`auth.py`][auth], [`recovery.py`][recovery], [`operator_auth.py`][operator-auth], route models | |
| `updated_at` is current | Every writer | No trigger. |
| `session_event` is append-only | Convention | No trigger. |
| Code attempt limits and rate limits | [`recovery.py`][recovery], [`operator_auth.py`][operator-auth] | |
| Only operators, and only admins where required, act on operator routes | [`operator_auth.py`][operator-auth] | |

## 7. Migrations

### 7.1 History

| Revision | Date | What it changed | Decision |
|---|---|---|---|
| [`0001`][m0001] | 2026-11-21 | Initial schema: `auth_nonce`, `device`, `residence`, `resident` (address only), `container`, `device_message`, `deposit_session` with `one_active_session_per_container` and `deposit_session_state_idx`, `session_event`. | [ADR 0005][adr-0005], [architecture, section 5][architecture] |
| [`0002`][m0002] | 2026-11-21 | `material_price` and the `payout` outbox. | [ADR 0003][adr-0003], [ADR 0007][adr-0007] |
| [`0003`][m0003] | 2026-11-22 | `residence.opens_hour`, `closes_hour`, `slot_capacity` with their checks (existing rows: open all day, 20 spots); `booking`; `push_token`; the `notification` outbox. | [ADR 0008][adr-0008], [ADR 0009][adr-0009] |
| [`0004`][m0004] | 2026-11-22 | `resident.owner_address` (backfilled from `address`, then NOT NULL and unique), `email`, `email_verified_at`; `email_code`; `account_recovery` with its two partial unique indexes; the `email_message` outbox. | [ADR 0010][adr-0010] |
| [`0005`][m0005] | 2026-11-22 | `host`. Each residence becomes a host with the same id (`residential`). `residence` is renamed `site`, with its primary key and checks; `site.host_id` (backfilled, NOT NULL, FK, index); `container.residence_id` renamed `site_id`, with its FK, plus an index. | [ADR 0011][adr-0011] |
| [`0006`][m0006] | 2026-11-22 | `bag`, `collector`, `collection` with `one_active_collection_per_container`, `collection_fill` with `one_open_fill_per_collection`, `incident`; `deposit_session.collection_id`. | [ADR 0012][adr-0012] |
| [`0007`][m0007] | 2026-11-22 | `sale`, `sale_line`, `settlement` with `one_settlement_per_party`. | [ADR 0013][adr-0013] |
| [`0008`][m0008] | 2026-11-22 | `operator`, `operator_code`. | [ADR 0014][adr-0014] |
| [`0011`][m0011] | 2026-11-23 | `resident.privacy_version`, `privacy_accepted_at`: the data-processing policy each participant accepted. | [ADR 0028](adr/0028-pilot-readiness.md) |
| [`0010`][m0010] | 2026-11-22 | `certificate`, `impact_claim` with `one_claim_per_deposit_attribute`. | [ADR 0027](adr/0027-impact-certificates.md) |
| [`0009`][m0009] | 2026-11-22 | The three CHECKs the models declared but no migration created (`container.area_mm2`, `container.depth_mm`, `material_price.cop_per_kg`); operator identity columns widened to 254. | section 9 below |

The dates are the `Create Date` lines of the migration files. Every migration has a downgrade.
Downgrades drop the tables and columns their upgrade added, so the data in them is lost.

### 7.2 Creating a migration

1. **Set up a scratch database.** Do not autogenerate against a database you care about.

   ```bash
   cd apps/api
   docker compose -f dev/compose.yml up -d
   docker compose -f dev/compose.yml exec postgres createdb -U zyrcle zyrcle_scratch
   export ZYRCLE_DATABASE_URL=postgresql+asyncpg://zyrcle:zyrcle@localhost:5432/zyrcle_scratch
   .venv/bin/alembic upgrade head
   ```

2. **Change `models.py`.** Give every CHECK constraint and every index an explicit `name=`, using
   the conventions in [section 1](#naming-conventions). An unnamed `CheckConstraint` written inline
   on a column is invisible to autogenerate; that is how three CHECKs were lost
   ([section 9](#9-discrepancies-found-while-writing-this-and-what-happened-to-them)).

3. **Generate the migration.** Revision ids are sequential four-digit strings.

   ```bash
   .venv/bin/alembic revision --autogenerate --rev-id 0009 -m "what changes"
   ```

   This writes `migrations/versions/0009_what_changes.py`.

4. **Review it by hand.** Autogenerate is a draft.
   - It does not detect CHECK constraints. Add `op.create_check_constraint(...)` and
     `op.drop_constraint(..., type_="check")` yourself, with the same names as `models.py`.
   - It does not detect renames. A renamed table or column shows up as a drop plus an add, which
     loses data. Replace it with `op.rename_table` or `op.alter_column(..., new_column_name=...)`,
     and rename the primary key, foreign keys and checks too, as [`0005`][m0005] does.
   - It does not compare server defaults (`compare_server_default` is not set in
     [`env.py`][env]).
   - Check every partial index's `WHERE` clause against `models.py`.
   - A new NOT NULL column on a table with rows: add it nullable, backfill with `op.execute`, then
     set NOT NULL, as [`0004`][m0004] and [`0005`][m0005] do.
   - Changing a value list (for example `PAYOUT_STATUSES`) means dropping and recreating the named
     CHECK.
   - Write a downgrade that reverses the upgrade, renames included.
   - Name the ADR in the migration's docstring when a decision drives the change.

5. **Test upgrade, downgrade and upgrade on a database with rows.** An empty database hides
   backfill and constraint problems. One way to get realistic rows is to run the test suite
   against the scratch database: it drops the schema, migrates to head, and leaves its rows behind.
   It needs the development broker ([API README][api-readme]).

   ```bash
   ZYRCLE_TEST_DATABASE_URL=$ZYRCLE_DATABASE_URL .venv/bin/pytest -q
   .venv/bin/alembic downgrade -1
   .venv/bin/alembic upgrade head
   ```

6. **Check that models and migrations agree.**

   ```bash
   .venv/bin/alembic check    # must report no new upgrade operations
   .venv/bin/alembic heads    # must print exactly one head
   ```

   CI runs `alembic upgrade head` and `alembic check` on an empty database. Remember that
   `alembic check` does not see CHECK constraints or server defaults.

7. **Deploy.** In production, the `migrate` service of the [deploy compose file][deploy-compose]
   runs `alembic upgrade head` with the new API image.

## 8. Data that must never be stored

1. **Plaintext one-time codes.** `email_code.code_hash` and `operator_code.code_hash` hold
   HMAC-SHA256 digests keyed with `settings.jwt_secret`. The key comes from the environment and is
   never in the database. Rotating `jwt_secret` invalidates every outstanding code, and every
   session token as well.
2. **Code emails after sending.** The plaintext code exists in `email_message` (subject and both
   bodies) only while the row is `pending`. When the worker marks a `code_*` email `sent` or
   `failed`, it replaces the subject and empties the bodies. A code email older than 10 minutes
   fails without being sent, and is blanked the same way. [Section 9](#9-discrepancies-found)
   describes a case where this does not happen.
3. **Private keys.** No column holds a private key or a seed phrase. The database holds only public
   material: addresses, device public keys and transaction hashes.
   - The Treasury oracle, operator and guardian keys are files on the server
     ([ADR 0022][adr-0022]). Settings name them (`oracle_key_file`, `operator_key_file`,
     `guardian_key_file`) and [`main.py`][main] loads them into memory at startup.
   - Participants' phone keys stay on the phone ([ADR 0006][adr-0006]).
   - Device signing keys stay on the device.
4. **Secrets and tokens.** `jwt_secret`, `operator_token`, the Resend API key and the Expo access
   token come from environment settings. JWTs are not stored. A participant's session ends when
   `resident.owner_address` no longer matches the token's key; an operator's ends when
   `operator.active` is false.

Sensitive data that is stored on purpose, and needs care:

- **Email addresses:** `resident.email`, `email_code.email` (including addresses with no account),
  `email_message.to` (kept after sending), `operator.email` and `operator_code.email`.
- **Device access codes in plaintext:** `device.current_code` and `device.previous_code`. The
  server must compare them, and each lives at most 60 seconds. Public views must never return them.
  Only the demo routes in [`demo.py`][demo], mounted only in demo mode, show the live QR.
- **Wallet addresses**, which link a participant to their on-chain balance and history.

## 9. Discrepancies found while writing this, and what happened to them

Found on 2026-11-22 by comparing the code with its comments, docstrings and ADRs.

| # | Discrepancy | Resolution |
|---|---|---|
| 1 | The CHECKs `container.area_mm2 > 0`, `container.depth_mm > 0` and `material_price.cop_per_kg >= 0` were declared in `models.py` but no migration created them (`alembic check` does not compare CHECKs) | Fixed: migration `0009` creates them with explicit names, and `models.py` names them |
| 2 | `account_recovery.cancelled_by` comment omitted `replaced` | Fixed: comment updated |
| 3 | `SaleLine` docstring did not show every transition | Fixed: docstring matches section 4.4 |
| 4 | `CollectionFill` docstring did not mention the 10 g noise floor | Fixed: docstring updated |
| 5 | `material_price.source = 'sales'` is never written | Documented as planned: prices from confirmed sales are not built yet |
| 6 | Operator identity columns were `varchar(64)`, operator emails up to 254 | Fixed: migration `0009` widens `reviewed_by`, `resolved_by`, `recorded_by`, `confirmed_by` to 254 |
| 7 | Operator code emails were queued even with email off, so the plaintext code stayed `pending` | Fixed: no code email is written when email is off |
| 8 | ADR 0012 said only credited deposits are linked to a collection; the code also links `review` and `rejected` ones | The code is right (their material is inside); ADR 0012 amended |
| 9 | Completing a recovery deleted the new phone's resident even if an operator had made it a collector, so the recovery could never finish | Fixed: the collector role moves to the account before the delete |

[models]: ../apps/api/src/zyrcle_api/models.py
[versions]: ../apps/api/migrations/versions/
[env]: ../apps/api/migrations/env.py
[db]: ../apps/api/src/zyrcle_api/db.py
[config]: ../apps/api/src/zyrcle_api/config.py
[main]: ../apps/api/src/zyrcle_api/main.py
[api]: ../apps/api/src/zyrcle_api/api.py
[auth]: ../apps/api/src/zyrcle_api/auth.py
[operator-auth]: ../apps/api/src/zyrcle_api/operator_auth.py
[sessions]: ../apps/api/src/zyrcle_api/sessions.py
[machine]: ../apps/api/src/zyrcle_api/domain/session_machine.py
[verification]: ../apps/api/src/zyrcle_api/domain/verification.py
[pricing]: ../apps/api/src/zyrcle_api/pricing.py
[payouts]: ../apps/api/src/zyrcle_api/payouts.py
[bookings]: ../apps/api/src/zyrcle_api/bookings.py
[collection]: ../apps/api/src/zyrcle_api/collection.py
[collection-routes]: ../apps/api/src/zyrcle_api/collection_routes.py
[sale-routes]: ../apps/api/src/zyrcle_api/sale_routes.py
[settlement]: ../apps/api/src/zyrcle_api/settlement.py
[notifications]: ../apps/api/src/zyrcle_api/notifications.py
[mail]: ../apps/api/src/zyrcle_api/mail.py
[recovery]: ../apps/api/src/zyrcle_api/recovery.py
[public]: ../apps/api/src/zyrcle_api/public.py
[chain]: ../apps/api/src/zyrcle_api/chain.py
[demo]: ../apps/api/src/zyrcle_api/demo.py
[demo-seed]: ../apps/api/src/zyrcle_api/demo_seed.py
[treasury]: ../chain/src/Treasury.sol
[conftest]: ../apps/api/tests/conftest.py
[api-readme]: ../apps/api/README.md
[dev-compose]: ../apps/api/dev/compose.yml
[deploy-compose]: ../deploy/compose.yml
[ci]: ../.github/workflows/ci.yml
[architecture]: architecture.md
[device-protocol]: device-protocol.md
[m0001]: ../apps/api/migrations/versions/0001_initial_schema.py
[m0002]: ../apps/api/migrations/versions/0002_prices_and_payouts.py
[m0003]: ../apps/api/migrations/versions/0003_slots_and_notifications.py
[m0004]: ../apps/api/migrations/versions/0004_accounts_and_recovery.py
[m0005]: ../apps/api/migrations/versions/0005_hosts_and_sites.py
[m0006]: ../apps/api/migrations/versions/0006_collection_bags_and_incidents.py
[m0007]: ../apps/api/migrations/versions/0007_sales_and_settlement.py
[m0008]: ../apps/api/migrations/versions/0008_operators.py
[m0009]: ../apps/api/migrations/versions/0009_checks_and_operator_names.py
[m0010]: ../apps/api/migrations/versions/0010_impact_certificates.py
[m0011]: ../apps/api/migrations/versions/0011_privacy_consent.py
[adr-0002]: adr/0002-own-avalanche-l1.md
[adr-0003]: adr/0003-advance-and-settlement.md
[adr-0005]: adr/0005-device-link-mqtt.md
[adr-0006]: adr/0006-expo-mobile.md
[adr-0007]: adr/0007-on-chain-treasury.md
[adr-0008]: adr/0008-push-notifications.md
[adr-0009]: adr/0009-time-slots.md
[adr-0010]: adr/0010-smart-accounts-and-recovery.md
[adr-0011]: adr/0011-hosts-and-sites.md
[adr-0012]: adr/0012-collection-and-bags.md
[adr-0013]: adr/0013-sale-and-settlement.md
[adr-0014]: adr/0014-operator-accounts.md
[adr-0020]: adr/0020-single-vps-docker-compose.md
[adr-0022]: adr/0022-keys-secrets-and-production-changes.md
