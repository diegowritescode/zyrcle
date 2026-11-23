# ADR 0031: Every party's journey tested in CI, and coverage that only goes up

- Status: proposed (2026-11-23)
- Decided by: Claude, building block 3 (M8) under ADR 0030, which Diego confirmed. Not yet
  confirmed.

## Context
Until block 3 the backend and the contracts had thorough tests, but the web and mobile apps had none
in the repository. Every screen was checked by walkthroughs that Claude ran by hand from a scratch
folder, and every change went straight to production (ADR 0020). The VPS has no memory for a second,
permanent staging copy.

## Decision
- **End-to-end tests live in `e2e/`** and drive real browsers with Playwright: one journey for a day
  on campus (deposits, the console, a collection from the phone, a sale settled on chain, an impact
  certificate verified against the chain and its IPFS copy, a merchant paid from a phone and paid
  out in pesos) and one for a lost phone (recovery with the 48-hour wait). Steps run in order and
  build on each other, like the day they describe. A step fails on any browser error other than the
  4xx answers it causes on purpose.
- **The pre-production check runs in CI on every push and pull request.** `e2e/stack/up.sh` starts
  the whole system from the commit's code on one machine: Postgres, Mosquitto, anvil with the
  NativeMinter stand-in as the chain, the simulator, the API, and stand-ins for Pinata and an IPFS
  gateway; emails are written to the API's log. `e2e/stack/apps.sh` builds the web app and the
  mobile app's web export against it. The Docker images are still built and checked by their own
  job; the end-to-end job runs the same code without them, which keeps it simple and fast, and
  leaves out only what the images add (nginx, its security headers, the container users).
- **The release waits for it.** Images are published only for commits whose CI passed, so a broken
  journey cannot reach production.
- **Unit tests where logic hides behind screens:** the certificate check of the web app (tampered
  leaves, a different root, a different IPFS copy, a gateway that is down) and the mobile app's push
  token registration (the loop of the first APK) and turn reminders, with native modules replaced by
  stand-ins. Vitest, the same as the shared client.
- **Coverage is measured and has a floor that only goes up:** the API at 75 % of lines (76 % measured
  on 2026-11-23), the shared client at 50 % (53 %). The web app's coverage is shown without a floor,
  since its pages are tested end to end.

## Consequences
- A pull request that breaks any party's screen fails before it can be deployed.
- The end-to-end job adds several minutes to CI and installs Chromium.
- Running the stack locally and the backend tests at the same time collides on the broker's device
  ids; `e2e/stack/down.sh` stops the stack first.
- The nginx configuration and security headers are not exercised by the journeys; a change there
  still needs a look at the live site.
