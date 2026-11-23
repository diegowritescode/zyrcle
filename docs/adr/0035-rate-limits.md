# ADR 0035: Rate limits on the whole API, per account, and per address only where needed

- Status: proposed (2026-11-23)
- Decided by: Claude, building block 3 (M12) under ADR 0030, which Diego confirmed. Not yet
  confirmed.

## Context
Only emailed codes had limits in the API (per address and per day). Traefik limits each source
address at the edge (20 requests a second on average, bursts of 60), which stops a flood but treats
a whole campus behind one public address as one caller, and says nothing about a single account
hammering one route.

## Decision
- **Token buckets in the API process**, refilled steadily, one per class of route and caller:

  | Class | Counted by | Per minute |
  |---|---|---|
  | Emailed codes (ask, use, recovery, operator sign-in) | IP address | 20 |
  | Phone sign-in (nonce, signature) | IP address | 120 |
  | Writes | account, else IP address | 120 |
  | Reads | account, else IP address | 600 |

- **Accounts, not addresses, for signed-in callers**, because a campus puts hundreds of phones
  behind one address. A token counts as an account only when its signature checks, so inventing
  tokens does not give anyone fresh buckets.
- **The address our proxy saw.** The last entry of `X-Forwarded-For` (Traefik adds it; one hop),
  never the first, which the client writes.
- **Answer `429` with `rate_limited` and `Retry-After`**, wrapped by CORS so a browser can read it;
  the apps say it in plain Spanish. `/health`, preflights and the WebSocket are not limited.
- **Off in the backend test suite**, which signs in hundreds of residents from one address; the
  limits have their own tests, and the end-to-end journeys run with them on.

## Consequences
- One account cannot flood a route, and codes cannot be guessed or mailed in bulk from one address.
- The buckets live in one process: running several API instances would need a shared store (Redis
  or Postgres) for the same guarantee.
- Traefik's edge limit per address still applies. For a pilot where many people share a campus
  address, it may need raising, or its source taken from a header Traefik trusts.
