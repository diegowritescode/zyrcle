# ADR 0033: Error reports to Sentry without personal data, and an uptime check from outside

- Status: proposed (2026-11-23)
- Decided by: Claude, building block 3 (M10) under ADR 0030, which Diego confirmed. Not yet
  confirmed.

## Context
The health report (ADR 0028) sees queues, the chain and gas from inside the API, and emails admins.
Nothing saw an error with its context, and nothing noticed if the whole VPS, Traefik or the API
went down, because the checker would be down with them.

## Decision
- **Sentry** in the API (`sentry-sdk`), the web app (`@sentry/react`) and the mobile app
  (`@sentry/react-native`). Each reports unhandled errors and, in the API, every logged exception
  (the workers log their failures that way), named by the commit (`ZYRCLE_RELEASE`, `VITE_RELEASE`)
  or the app's version. Off without a DSN; the web app does not even load the SDK without one.
- **Reports carry no personal data.** `send_default_pii` is off, and one rule set, in the API
  (`observability.py`) and in the shared client (`scrub.ts`), runs before anything leaves: email
  addresses, hex strings of 64 characters or more (private keys, signatures), bearer tokens and JWTs
  become `[redacted]`; request bodies, cookies, headers and the user are dropped. Account addresses
  stay: they are public on the chain and are what an operator needs to find a stuck payment.
- **Uptime from outside:** a scheduled GitHub workflow, every 10 minutes, checks the API (and its
  broker connection), the web app and the public RPC. A failure opens or updates an issue labelled
  `uptime`, which GitHub notifies; a healthy check closes it. The repository is public, so the runs
  cost nothing.
- **Where the DSNs go:** `SENTRY_DSN_API` in `deploy/.env` (Diego, over SSH), the repository
  variable `SENTRY_DSN_WEB` for the web image, `EXPO_PUBLIC_SENTRY_DSN` as an EAS variable for the
  app. The web page's Content-Security-Policy allows Sentry's ingest hosts.

## Consequences
- Errors arrive with their stack and the commit, without anyone reading logs on the VPS.
- Sentry is a third party that receives stack traces and account addresses; the scrubbing rules are
  tested in both languages.
- The mobile app now includes a native module; it takes effect in the next EAS build. Source maps
  for the app are not uploaded yet, so its stack traces point at the bundle.
- GitHub can delay scheduled checks by some minutes and pauses them after 60 days without activity
  in the repository. A phone alert needs a service such as UptimeRobot, which Diego can add.
