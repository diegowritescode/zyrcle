# Blocks 3 and 4: from a working loop to a product every party relies on

> Status: **planned** (2026-11-23). v1 blocks 1 and 2 are deployed ([roadmap-v1.md](roadmap-v1.md)).
> Scope and order: [ADR 0030](adr/0030-blocks-3-and-4.md).

## Why

v1 closes the loop once, on a simulator, with an operator doing much of the work by hand. Before a
real campus depends on it, three things are missing:

- **Safety nets.** The web and mobile apps have no tests of their own in the repository, every
  change goes straight to production, errors are seen only when someone looks, and losing the VPS
  loses everything, keys included.
- **Less manual work.** The operator types every scale ticket and matches every bank deposit by eye.
- **A reason to come back, for each party.** Participants cannot follow a deposit to its payment or
  see where to spend; collectors do not know which container is full; hosts get a certificate they
  must fetch and print themselves; merchants cannot export their books.

## How the work is split

- **Block 3, foundations and operations (M8 to M17):** everything that makes changes safe, keeps the
  system alive without watching it, protects the keys, and takes the manual work off the operator.
  It goes first because block 4 is built on top of it.
- **Block 4, every party (M18 to M23):** what each party sees and uses: participant, collector,
  host, merchant and collection center. It ends with a new Android build.

Same method as v1 (ADR 0026): Claude builds each block on its own, every decision gets an ADR, and
Diego reviews, confirms and authorizes each deploy and each chain transaction. Features that need an
account Diego must open ship switched off, like the IPFS copy did, and switch on when he places the
key on the server.

```
Block 3                                         Block 4
M8  Safety net (tests in CI) ──┬──────────────► M18 Participant: timeline, impact, where to spend
M9  Stricter deploys           │                M19 Collector: fill alerts, earnings
M10 Error and uptime monitoring│                M20 Host: monthly PDF, goals, ranking data
M11 Off-site encrypted backups │                M21 Merchant: accounting export
M12 Rate limits                │                M22 Collection center portal
M13 Cleanup and refactor ◄─────┘                M23 Release: new APK, aliases removed
M14 Prices per collection center ──► M15 Ticket reading with AI ──► M16 Bank statement matching
M17 Keys: own guardian key, admin powers behind a multisig
```

## Block 3: foundations and operations

### M8. Safety net: the whole system tested in CI
- **What:** the browser walkthroughs that today live outside the repository (deposit, collection,
  sale, settlement, certificate with its IPFS copy, merchant payment and redemption) become
  Playwright tests in `e2e/`. A CI job starts the real Docker images of the commit with Postgres,
  the broker, a local chain (anvil with the NativeMinter mock), the simulator and stand-ins for
  Pinata, Resend and Expo, then runs every walkthrough in Chromium against the web app and the
  mobile app exported for the web. Unit tests for web and mobile components that hold logic. Test
  coverage measured for the API (pytest-cov), the shared client and the web app (Vitest), shown in
  each CI run, with a floor at today's level that only goes up.
- **Why this first:** it is a full copy of production, rebuilt for every commit, without paying for
  a second server. A permanent staging server needs more memory than the VPS has (ADR 0020); that
  stays a decision for later.
- **Done when:** a pull request that breaks any screen of any party fails CI before it can be
  deployed.

### M9. Stricter deploys
- **What:** the release records each image's digest (its exact fingerprint) and `deploy.sh` runs
  images by digest, not by tag. `deploy.sh` refuses to run if the checkout is not the commit being
  deployed, backs up the database before migrating, pulls each image with a timeout and retries
  (the hang of 2026-11-23), and appends every deploy to a history file (date, commit, digests,
  migration revision). A manual run of the release workflow fails unless CI passed for that commit.
  Base images (Postgres, Mosquitto, Python, nginx) pinned by digest, with automatic update pull
  requests.
- **Done when:** a deploy can be traced to exact images and rolled back from the history file.

### M10. Error and uptime monitoring
- **What:** Sentry in the API, the web app and the mobile app, each error with its context and no
  personal data (emails, tokens and keys scrubbed). A scheduled GitHub workflow checks every few
  minutes that the API, the web app and the public RPC answer and that the chain produces blocks;
  when one fails it opens an issue, which GitHub emails to Diego. Off until the Sentry DSNs are set.
- **Needs from Diego:** a Sentry account (free plan) and its three DSNs, placed on the server and in
  EAS; optionally an UptimeRobot account for checks with phone alerts.
- **Done when:** a forced error reaches Sentry with its context, and stopping the API opens an issue.

### M11. Off-site encrypted backups
- **What:** the daily database dump, plus a weekly bundle of the validator identity (staking key,
  TLS certificate, BLS key) and the key files, encrypted with `age` before they leave the VPS, then
  copied to object storage with `rclone`. Both run as containers, so nothing is installed on the
  host. The public key sits on the server; the private key only with Diego, offline. A documented
  restore drill: download, decrypt on Diego's machine, restore into a throwaway database.
- **Needs from Diego:** a bucket (Cloudflare R2 recommended: 10 GB free and no download fees) with a
  write-only key, and an `age` key pair he generates on his own machine.
- **Done when:** a backup made on the VPS is restored from the bucket on another machine.

### M12. Rate limits on the whole API
- **What:** limits per IP and per account, by route class: sign-in and codes strict, writes medium,
  public reads lenient. Answers `429` with `Retry-After`, and the apps say it in plain Spanish.
  Kept in the API process, which is enough for one instance; more instances would need a shared
  store, written down in the ADR.
- **Done when:** a burst against any route is cut off without affecting other users.

### M13. Cleanup and refactor
- **What:** split the largest modules by responsibility, with M8's tests around every move:
  `models.py` into a package per domain, account recovery into service, worker and routes, and the
  same for sessions and collection. No behavior changes. The deprecated `residence` routes and
  fields wait for M23, once the new Android build is in use.
- **Done when:** no module is over about 400 lines and every test still passes.

### M14. Prices per collection center
- **What:** collection centers become records (name, tax id, address, contact). Each has its
  reference price per material, and each site sells to a center. Advances use the price of the
  center the site sells to, falling back to the general table. The console suggests a price from
  that center's recent confirmed sales (median of the last 90 days), and the operator accepts or
  edits it. Final payments already follow the real sale (ADR 0013); this changes only the advance.
- **Done when:** two sites selling to centers with different prices get different advances, and
  each sale records its center.

### M15. Reading the scale ticket with AI
- **What:** the operator photographs the ticket in the console. The API sends it to Claude
  (`claude-opus-5-5`) with a fixed JSON schema (structured output): center, ticket number, date,
  and per material the kilograms, price per kilogram and amount, plus the total. The API checks the
  arithmetic (kilograms times price, lines against the total), proposes the bags each line belongs
  to, and the operator reviews and corrects before saving. Nothing is saved without a person. Kept
  for audit: the photo, the model and request id, what the model read, and who accepted it. About
  US$0.03 per ticket. Off without an Anthropic key.
- **Needs from Diego:** an Anthropic API key with a monthly spending limit, placed on the server;
  photos of real tickets from the center the campus will use, to test against (synthetic ones
  until then).
- **Done when:** a ticket photo becomes a sale with every line filled, and every figure the model
  read can be traced.

### M16. Matching the bank statement
- **What:** the operator uploads the statement exported from the bank (CSV or Excel; Bancolombia
  first, plus a generic column mapping). The API proposes which deposit pays which sale (same
  amount, date within a few days of the sale, reference or center name in the description) and
  which outgoing transfer pays which redemption, each with a score. The operator confirms with one
  click; nothing is confirmed automatically. Bank APIs wait until open banking in Colombia is
  usable.
- **Needs from Diego:** a real statement export, anonymized, to test the parser.
- **Done when:** a statement with several deposits proposes the right sale for each.

### M17. Keys: own guardian key, admin powers behind a multisig
- **What:** today one L1 admin key, kept on the VPS, controls every precompile, the validator
  manager and the contracts' admin roles, and the guardian shares the oracle key.
  - The guardian (recoveries and relayed payments) gets its own key and gas (ADR 0010, 0028).
  - Audited Safe contracts (v1.4.1) are deployed on ZyrcleChain. A 2-of-3 Safe receives every admin
    power: the Treasury and AccountFactory admin roles, the admin of the NativeMinter and the other
    allow lists, and the validator manager. Safe transactions are proposed from the CLI and signed
    from the console with a browser wallet or offline from key files.
  - The L1 admin key then leaves the VPS for Diego's offline inventory. The keys that must sign on
    their own (oracle, operator, guardian) stay on the server with the least power each needs and
    the contract caps that already limit them.
- **Needs from Diego:** three signer addresses (for example a browser wallet, a phone wallet and an
  offline backup) and approval of each transaction on Fuji.
- **Done when:** no single key on the server can mint, change roles or touch the validators.

## Block 4: every party

### M18. Participant
- **Each deposit, step by step:** deposited, verified, collected, sold, paid, with the date and the
  amount of each step, and a push notification when it is sold and when it is paid.
- **Personal impact:** kilograms verified and sold, and CO2e avoided by what was sold (same factors
  and rule as the certificates, ADR 0027), per material and per month.
- **Where to spend:** the campus merchants with location, hours and what they sell, in the app and
  on the web.

### M19. Collector
- **Fill alerts:** each container's fill level from its contents and capacity; a push to the host's
  collectors when one passes 80 %; a list ordered by fill and by time since the last emptying.
- **Earnings:** what each collection paid, by month.

### M20. Host
- **Monthly certificate without asking:** on the first days of each month the system issues the
  previous month's certificates for hosts that opted in, waits for the anchor and the IPFS copy, and
  emails the host's contacts a formal PDF with a QR to the verification page, the CID and the anchor
  transaction.
- **Goals and comparison:** monthly kilogram goals per host or site, progress, and a comparison
  between sites (total kilograms, per participant, trend).
- **Data for sustainability rankings** such as UI GreenMetric: a yearly export of the figures its
  waste questionnaire asks for that Zyrcle can back (recycled waste by material, participants,
  campaigns), each with links to the certificates as evidence. The current questionnaire is
  checked when this milestone starts. The export says what it covers: only what went through
  Zyrcle, not the institution's total waste.

### M21. Merchant
- **Accounting export:** charges and redemptions for a date range, with tax id, references and
  transactions, as CSV and Excel, from the app and from the console.

### M22. Collection center portal
- **What:** the center's staff sign in with an email code, like operators. They register a purchase
  with the bag codes, weights, prices and the ticket photo, which becomes a sale draft. The operator
  only matches it with the bank. The center sees its history.
- **Needs:** a collection center willing to use it.

### M23. Release
- **What:** a new Android build with blocks 3 and 4, installed by Diego. Then the deprecated
  `residence` routes and fields are removed (ADR 0011, amendments). Every party's walkthrough runs
  in CI (M8).
- **Needs from Diego:** approval of the EAS build.

## What stays out

Cash-out of ZYR to pesos for participants (legal review first), tradable carbon or plastic credits
(v2), producer and SUI reports (the claim ledger prepares for them), iOS, the weighing station
hardware (track H in roadmap-v1, in parallel when there is budget), and the chain for real money
(Diego's decision, ADR 0028).
