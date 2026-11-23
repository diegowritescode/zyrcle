# ADR 0028: Pilot readiness: backups, alerts, consent, production switches

- Status: proposed (2026-11-23)
- Decided by: Claude proposed in v1 block 2 (M7). Not yet confirmed. Items marked **for Diego**
  need his decision or his accounts.

## Context
Before a real person's data or money touches Zyrcle, the roadmap's M7 asks for backups, monitoring,
a privacy policy with consent, a legal look at how ZYR is presented, the app in a store, a review of
the contracts and keys, and a decision about the chain. Some of this is code and configuration;
some needs a lawyer, money or Diego's accounts.

## Decision
- **Backups.** `deploy/backup.sh` writes a compressed `pg_dump` of the production database to
  `~/backups/zyrcle` on the VPS (directory `0700`, files `0600`), keeps 14 days, and
  `deploy/backup.sh --check FILE` restores a dump into a throwaway Postgres and counts its rows, so a
  backup is known to restore. It is meant to run daily from cron at 03:15. **For Diego:** installing
  the cron entry on the VPS, and where an off-site copy goes (nothing leaves the machine today).
- **Health and alerts.** `GET /v1/operator/health` reports every outbox (pending, failed, oldest),
  devices online, the broker, the chain's latest block and its age, the Treasury's mintable pesos,
  and the gas left on the oracle and operator keys. The console's summary shows it. A worker emails
  every active admin each warning at most once a day per kind. Thresholds: a queue stuck for
  30 minutes, any failed row, no block for 10 minutes (a validator without balance), less than
  100,000 COP mintable, less than 1 ZYR of gas on a key.
- **Consent (Ley 1581 de 2012).** The data-processing policy and the terms are pages of the web app
  (`/privacidad`, `/terminos`), both marked as drafts for legal review. Participants accept the
  policy in force from the apps; the API stores the version and the time (`resident.privacy_version`,
  `privacy_accepted_at`). `require_consent` makes accepting it a condition for depositing; it stays
  off until the pilot so apps installed before the consent screen keep working. The policy says
  plainly that payments on the chain are public and cannot be erased. **For Diego and a lawyer:**
  the contact channel, the treatment of minors on campuses, and the final text.
- **Production switches.** The interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are off in
  production (`ZYRCLE_DOCS_ENABLED=false`). A pilot deployment with real containers runs without the
  demo router and simulator (no `ZYRCLE_DEMO_SIMULATOR_URL`), because the demo lists live QR codes.
- **Contracts reviewed with Slither** (2026-11-23); triage in [security.md](../security.md). No
  finding needs a change before the pilot; the settlement loop will update its books before minting
  when the Treasury is redeployed for M6.
- **Keys.** Before the pilot the AccountFactory guardian gets its own key instead of sharing the
  oracle key, and the gas of the hot keys is refilled from the admin's float when the alert fires.
- **Still open, for Diego:** the legal framing of ZYR (closed-loop points, not electronic money),
  a Google Play developer account for the internal testing track, and the chain for real value
  (Fuji or a mainnet L1 and its monthly cost).

## Consequences
- An operator learns about a stuck queue or a dying validator from an email, not from a participant.
- Consent is recorded per version, so a new policy asks everyone again.
- Some M7 items cannot be closed by code; they are listed here until Diego decides them.
