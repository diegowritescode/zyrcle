# End-to-end tests

Every party's journey in a real browser, against the whole system started from this checkout
([ADR 0031](../docs/adr/0031-testing-and-the-pre-production-check.md)). CI runs them on every push
and pull request.

| File | What it walks through |
|---|---|
| `tests/journey.spec.ts` | A day on campus: the university's dashboard, a participant's deposits, the operator's console, a collection center and its prices, a collection from the phone, a sale read from a ticket photo, matched to the bank statement and settled on chain, an impact certificate verified against the chain and its IPFS copy, a merchant paid from a phone and paid out in pesos, matched to the statement |
| `tests/multisig.spec.ts` | The Safe: deployed with three owners, a wallet signs on the multisig page, a stranger cannot, a paper key signs on the command line, the proposal runs |
| `tests/recovery.spec.ts` | A lost phone: recovery email, the new phone, the 48-hour wait, the old phone locked out |

## The stack

The system runs from this checkout's source, not from the Docker images, which keep their own CI
job; the journeys therefore do not exercise nginx and its security headers.

| Piece | Port | What stands in for production |
|---|---|---|
| Chain | 8546 | anvil with the NativeMinter mock, the Treasury and the AccountFactory (`apps/api/dev/local_chain.py`) |
| Database, broker | 5432, 1883 | Postgres and Mosquitto from `apps/api/dev/compose.yml`; a fresh `zyrcle_e2e` database every run |
| Containers | 8091 | the simulator (`zyrcle-sim`), four devices |
| API | 8010 | `uvicorn` from `apps/api`; emails go to `api.log` |
| Web app, mobile app | 4180, 8092 | `vite build` and the mobile app's web export, served by [`stack/static.mjs`](stack/static.mjs) |
| External services | 8093 | [`stack/fake-services.mjs`](stack/fake-services.mjs): Pinata's `pinJSONToIPFS`, an IPFS gateway (`/ipfs/<cid>`), and Anthropic's Messages API, which answers the ticket reading a test sets |

## Run them

Needs Docker (for Postgres and Mosquitto), the API's virtualenv (`apps/api/.venv`), Foundry's
`anvil`, Node 22 and Google Chrome.

```bash
apps/api/dev/mosquitto/make-passwd.sh                # dev broker users, password "dev-password"
docker compose -f apps/api/dev/compose.yml up -d
(cd e2e && npm ci)
e2e/stack/up.sh        # chain, database, simulator, API, Pinata, IPFS and Anthropic stand-ins
e2e/stack/apps.sh      # web app on :4180, mobile app (web export) on :8092
(cd e2e && npm run typecheck && npx playwright test)
e2e/stack/down.sh      # before running the backend tests: both use the same device ids
```

The steps of each file run in order and build on each other, with one worker. A step fails on any
browser error other than the 4xx answers it causes on purpose. In CI a failed run is retried once
and keeps the logs and the Playwright report for 14 days.

Logs and state are in `e2e/.stack/` (`api.log` holds the emails, codes included). A failed step
keeps a trace: `npx playwright show-trace test-results/<step>/trace.zip`.

Settings: `E2E_PG` (Postgres URL without a database, default
`postgresql://zyrcle:zyrcle@localhost:5432`), `E2E_PY` (folder of the API's Python executables),
`E2E_STATE` (where the stack keeps its state).
