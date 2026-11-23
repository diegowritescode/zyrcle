# End-to-end tests

Every party's journey in a real browser, against the whole system started from this checkout
([ADR 0031](../docs/adr/0031-testing-and-the-pre-production-check.md)). CI runs them on every push
and pull request.

| File | What it walks through |
|---|---|
| `tests/journey.spec.ts` | A day on campus: the university's dashboard, a participant's deposits, the operator's console, a collection center and its prices, a collection from the phone, a sale read from a ticket photo, matched to the bank statement and settled on chain, an impact certificate verified against the chain and its IPFS copy, a merchant paid from a phone and paid out in pesos, matched to the statement |
| `tests/multisig.spec.ts` | The Safe: deployed with three owners, a wallet signs on the multisig page, a stranger cannot, a paper key signs on the command line, the proposal runs |
| `tests/recovery.spec.ts` | A lost phone: recovery email, the new phone, the 48-hour wait, the old phone locked out |

## Run them

Needs Docker (for Postgres and Mosquitto, from `apps/api/dev/compose.yml`), the API's virtualenv
(`apps/api/.venv`), Foundry's `anvil`, Node 22 and Google Chrome.

```bash
docker compose -f apps/api/dev/compose.yml up -d
(cd e2e && npm ci)
e2e/stack/up.sh        # chain, database, simulator, API, Pinata stand-in
e2e/stack/apps.sh      # web app on :4180, mobile app (web export) on :8092
(cd e2e && npx playwright test)
e2e/stack/down.sh      # before running the backend tests: both use the same device ids
```

Logs and state are in `e2e/.stack/` (`api.log` holds the emails, codes included). A failed step
keeps a trace: `npx playwright show-trace test-results/<step>/trace.zip`.

Settings: `E2E_PG` (Postgres URL without a database, default
`postgresql://zyrcle:zyrcle@localhost:5432`), `E2E_PY` (folder of the API's Python executables),
`E2E_STATE` (where the stack keeps its state).
