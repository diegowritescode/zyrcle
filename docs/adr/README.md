# Architecture decision records

Every decision about Zyrcle's design, defaults and operation is written down here, with who made it
and when it was confirmed. That includes the small ones: a percentage, a tolerance, a timeout, a
code format. If a number in the code changes how money, weight or trust is handled, it has a record.

## How a decision is recorded

- **One file per decision**, numbered in the order it was taken: `NNNN-short-title.md`. Sections:
  Context (why it had to be decided), Decision (what, with the values), Consequences (what it costs
  and what it leaves open).
- **Status and date** on the second line: `proposed`, `accepted`, `superseded by NNNN` or
  `deprecated`.
- **Decided by** on the third line: who proposed it and who confirmed it, and how. Claude works on
  blocks of the roadmap on its own and proposes decisions; Diego confirms them when he reviews the
  block. A record stays `proposed` until Diego confirms it, and the confirmation is quoted.
- **Accepted records are not rewritten.** A change to an accepted decision is either a new record
  that supersedes it, or, for a detail, an entry under **Amendments** at the end of the record, with
  its date and who decided it. The text above the amendments stays as it was decided.
- **Fixes that change a rule are amendments too**, even when they come from a bug. The commit that
  makes the change names the record.
- Every block of work ends with the list of decisions it took, for Diego to confirm.

## Index

| ADR | Decision | Status | Decided by |
|---|---|---|---|
| — | Decisions of the hackathon build (May 2025) | not recorded at the time | see [history](../history.md#2025-the-hackathon) |
| [0001](0001-monorepo.md) | One monorepo with the hackathon history imported | accepted 2026-11-21 | not recorded (before this log) |
| [0002](0002-own-avalanche-l1.md) | Own Avalanche L1 with ZYR as the native coin | accepted 2026-11-21 | not recorded (before this log) |
| [0003](0003-advance-and-settlement.md) | Pay residents an advance plus a settlement | accepted 2026-11-21 | not recorded (before this log) |
| [0004](0004-closed-loop-first.md) | Closed loop first, fiat ramp later | accepted 2026-11-21 | not recorded (before this log) |
| [0005](0005-device-link-mqtt.md) | MQTT to the container, WebSocket to the app | accepted 2026-11-21 | not recorded (before this log) |
| [0006](0006-expo-mobile.md) | Expo (React Native) for the resident app | accepted 2026-11-21 | not recorded (before this log) |
| [0007](0007-on-chain-treasury.md) | On-chain Treasury that mints only against recorded pesos | accepted 2026-11-22 | not recorded (before this log) |
| [0008](0008-push-notifications.md) | Push through an outbox and Expo's push service | accepted 2026-11-22 | not recorded (before this log) |
| [0009](0009-time-slots.md) | Hourly time slots with walk-ins | accepted 2026-11-22 | not recorded (before this log) |
| [0010](0010-smart-accounts-and-recovery.md) | Smart accounts with guardian recovery, proven by email | accepted 2026-11-22 | Diego chose the smart account and an email code sent with Resend; Claude designed it |
| [0011](0011-hosts-and-sites.md) | Hosts and sites | accepted 2026-11-22 | Claude proposed (v1 block 1); Diego answered "sí, ok, te autorizo" to the list of block 1 decisions |
| [0012](0012-collection-and-bags.md) | Collection and bags weighed by the container | accepted 2026-11-22 | as 0011 |
| [0013](0013-sale-and-settlement.md) | Sale, bank match, settlement; shares 65/15/10/10 | accepted 2026-11-22 | as 0011; Diego confirmed the shares on 2026-11-23 |
| [0014](0014-operator-accounts.md) | Operator accounts and the console | accepted 2026-11-22 | as 0011 |
| [0015](0015-android-builds.md) | Android builds: EAS, Firebase push, ARM only | accepted 2026-11-23 | Claude proposed; Diego set up the Expo and Firebase accounts and confirmed it |
| [0016](0016-rebuild-not-patch.md) | Rebuild the hackathon project instead of patching it | accepted 2026-11-21, recorded later | Diego set the goal; Claude proposed the approach |
| [0017](0017-proprietary-license.md) | Proprietary license, all rights reserved | accepted 2026-11-22, recorded later | Diego |
| [0018](0018-keep-the-hackathon-design.md) | Keep the hackathon design; Spanish copy without invented numbers | accepted 2026-11-22, recorded later | Diego (design); Claude (copy rules) |
| [0019](0019-remove-legacy-code.md) | Remove legacy code, keep it at tag v0-hackathon | accepted 2026-11-22, recorded later | Claude proposed; Diego approved |
| [0020](0020-single-vps-docker-compose.md) | One VPS with Docker Compose; images by full commit SHA | accepted 2026-11-22, recorded later | Claude proposed; Diego provided the VPS and domain |
| [0021](0021-l1-operations.md) | Operate the L1 with platform-cli; one validator, fee topped up by hand | accepted 2026-11-21, recorded later | Claude |
| [0022](0022-keys-secrets-and-production-changes.md) | Keys, secrets, and who may change production | accepted 2026-11-22, recorded later | Diego |
| [0023](0023-testnet-economics.md) | Testnet money: simulated seed and test prices | accepted 2026-11-22, recorded later | Diego (seed amount); Claude (prices, limits); Diego confirmed the advance limits on 2026-11-23 |
| [0024](0024-monorepo-tooling.md) | No npm workspaces, shared TS client, StyleSheet on mobile | accepted 2026-11-22, recorded later | Claude |
| [0025](0025-documentation-as-code.md) | Documentation in the repository, changed with the code | accepted 2026-11-22 | Diego asked; Claude proposed the structure |
| [0026](0026-v1-scope-and-delivery.md) | v1: one university campus, delivered in two reviewed blocks | accepted 2026-11-22 | Diego (university, two blocks); Claude (scope, milestones) |
| [0027](0027-impact-certificates.md) | Impact certificates: sold material only, EPA WARM v16, one claim per gram, anchored root; amended 2026-11-22 with a permanent copy on IPFS (Pinata) | accepted 2026-11-23 | Claude proposed (v1 block 2, M5); Diego asked for host certificates, chose the IPFS copy and confirmed it |
| [0028](0028-pilot-readiness.md) | Pilot readiness: backups, alerts, consent, production switches | accepted 2026-11-23 | Claude proposed (v1 block 2, M7); Diego confirmed it; several items still wait for him |
| [0029](0029-closed-loop-payments.md) | Paying campus merchants; redeeming ZYR for pesos; Treasury v3 | accepted 2026-11-23 | Claude proposed (v1 block 2, M6, after ADR 0004); Diego confirmed it |
| [0030](0030-blocks-3-and-4.md) | Blocks 3 and 4: foundations and operations first, then every party | accepted 2026-11-23 | Diego asked for one large plan in two blocks and confirmed it; Claude proposed the split, order and designs |
| [0031](0031-testing-and-the-pre-production-check.md) | Every party's journey tested in CI; coverage floors that only go up | proposed 2026-11-23 | Claude (block 3, M8); not yet confirmed |
| [0032](0032-deploys-pinned-recorded-and-backed-up.md) | Deploys pinned by digest, recorded, backed up before migrating; base images pinned | proposed 2026-11-23 | Claude (block 3, M9); not yet confirmed |
| [0033](0033-error-reports-and-uptime.md) | Error reports to Sentry without personal data; uptime check from outside | proposed 2026-11-23 | Claude (block 3, M10); not yet confirmed |
| [0034](0034-encrypted-off-site-backups.md) | Encrypted copies off the VPS: database, validator identity, keys | proposed 2026-11-23 | Claude (block 3, M11); not yet confirmed; needs Diego's bucket and age key |
| [0035](0035-rate-limits.md) | Rate limits on the whole API, per account, per address only for codes and sign-in | proposed 2026-11-23 | Claude (block 3, M12); not yet confirmed |

Records 0016 to 0024 describe decisions taken before this log existed. They were written on
2026-11-22 from the code, the commit history and the conversations, and keep the date each decision
was taken. Numbers follow the order records were written, not the order decisions were taken.

Later decisions get the next number when they are taken.
