# ADR 0030: Blocks 3 and 4: foundations and operations first, then every party

- Status: proposed (2026-11-23)
- Decided by: Diego asked on 2026-11-23 for one large plan covering everything Claude listed as
  missing, for every party and for the engineering, split into two large blocks ("quiero un bloque
  grande… podemos dividir el trabajo en dos bloques grandes"). Claude proposed the split, the order
  and the designs. Not yet confirmed.

## Context
v1 blocks 1 and 2 are deployed (ADR 0026). The loop closes on a simulator, with much of the
operation done by hand. A review on 2026-11-23 found what a real campus would need: tests for the
web and mobile apps, a pre-production check, error and uptime monitoring, backups off the VPS, one
admin key that controls the whole chain, rate limits only on email codes, large modules, and, per
party, features that give each one a reason to use the system.

## Decision
- **Two blocks** ([roadmap](../roadmap-blocks-3-4.md)).
  - Block 3, M8 to M17: the whole system tested in CI, stricter deploys, monitoring, off-site
    encrypted backups, rate limits, cleanup, prices per collection center, ticket reading with AI,
    bank statement matching, and the keys (own guardian key, admin powers behind a 2-of-3 Safe).
  - Block 4, M18 to M23: participant, collector, host, merchant and collection center features, and
    a release with a new Android build.
- **Block 3 goes first** because block 4 is built on its tests and its operator flows.
- **The pre-production check runs in CI**, against the real images of each commit with stand-ins
  for external services, instead of a permanent staging server the VPS has no memory for
  (ADR 0020). A permanent staging server stays open.
- **Features that need Diego's accounts ship switched off** and turn on when he places the key on
  the server (Sentry, the backup bucket, the Anthropic key), as the IPFS copy did (ADR 0027,
  amendment).
- **People stay in charge of money and claims:** the AI reads tickets and the system proposes bank
  matches, but an operator confirms every sale and every match.
- **Same method as v1:** Claude builds each block on its own; each milestone gets its own ADR when it
  is built; Diego reviews, confirms, and authorizes each deploy and each chain transaction by name.

## Consequences
- Block 3 changes little that participants see, but every later change becomes safer and the
  operator's work shorter.
- Diego has inputs to prepare in parallel: a Sentry account, a storage bucket and an `age` key pair,
  three signer addresses for the Safe, an Anthropic API key with a spending limit, real ticket photos
  and an anonymized bank statement, the hosts' contact emails, and later a willing collection center.
- Moving the admin powers to a Safe is hard to undo and is done only with his approval of each
  transaction.
