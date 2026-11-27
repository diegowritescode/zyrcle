# Zyrcle web app

The hackathon's interface (May 2025), kept as it was designed (eco palette, shadcn/ui components,
landing, the dashboard) and wired to the rebuilt backend in [`apps/api`](../api). Live at
https://zyrcle.deviego.xyz.

| Route | What it shows | Data |
|---|---|---|
| `/` | Landing | Live totals from `GET /v1/stats` instead of the hackathon's made-up figures |
| `/recycling` | The resident's deposit: scan the container's QR (camera or typed code), choose the material, live weight, "Terminé", verdict and payment; the resident's history with each deposit's steps and "Mi impacto"; and "Dónde gastar", the campus merchants ([ADR 0041](../../docs/adr/0041-participant-timeline-impact-and-where-to-spend.md)) | SIWE sign-in, `POST /v1/sessions`, WebSocket `/v1/sessions/{id}/live`, `GET /v1/me`, `GET /v1/me/impact`, `GET /v1/merchants` |
| `/sites` | A host's dashboard across its sites, or one site's: totals, kilos per day and material, pesos paid per day, each site's numbers or each container's fill level and weight; on a host's view, its goals this month with the comparison between sites ([ADR 0046](../../docs/adr/0046-host-monthly-report-goals-and-rankings.md)) and its impact certificates. `/residence` redirects here | `GET /v1/hosts/{id}/dashboard`, `GET /v1/sites/{id}/dashboard`, `GET /v1/hosts/{id}/progress`, `GET /v1/hosts/{id}/certificates` |
| `/console` | Operations console ([ADR 0014](../../docs/adr/0014-operator-accounts.md)): sign-in by email code, then the tabs below | `/v1/operator/*` |
| `/certificates/:id` | A host's impact certificate ([ADR 0027](../../docs/adr/0027-impact-certificates.md)): totals per material, CO2e avoided, print view, the PDF with a QR ([ADR 0046](../../docs/adr/0046-host-monthly-report-goals-and-rankings.md)), CSV of the deposits, and "Verificar", which recomputes the root in the browser and compares it with the anchor transaction on ZyrcleChain and with the copy on IPFS | `GET /v1/certificates/{id}`, the public RPC, the IPFS gateway |
| `/multisig` | "Firmar en el Safe" ([ADR 0040](../../docs/adr/0040-keys-guardian-and-multisig.md)): an owner of the Safe that holds ZyrcleChain's admin powers loads a proposal made with `zyrcle-api safe propose`, checks it, signs it with the browser wallet (`eth_signTypedData_v4`, adding ZyrcleChain if needed) and downloads or copies it for the next signer | the public RPC only |
| `/privacidad`, `/terminos` | The data-processing policy and terms of use, drafts for legal review ([ADR 0028](../../docs/adr/0028-pilot-readiness.md)) | none |
| `/container/:id` | A container's screen, simulated: the QR whose code rotates every 30 s | `GET /v1/demo/containers` |
| `/collectors`, `/marketplace` | What comes next (block 4 and later) | none |
| `/validator`, `/my-certificates` | Old hackathon links: they redirect to `/console` and `/sites` (hosts' certificates are listed on their dashboard) | none |

The console's tabs ([`src/pages/Console.tsx`](src/pages/Console.tsx), one component each in
[`src/components/console/`](src/components/console)):

| Tab | What the operator does there |
|---|---|
| Resumen | Pending work, the system's health ([ADR 0028](../../docs/adr/0028-pilot-readiness.md)), the Treasury, the containers |
| Revisión | Approve or reject deposits in review |
| Incidentes | Resolve mass-balance incidents with a note |
| Recolección | Name collectors and the institution whose containers they empty ([ADR 0042](../../docs/adr/0042-collector-fill-alerts-and-earnings.md)), print bag labels, follow collections |
| Ventas | Read the scale ticket from a photo ([ADR 0038](../../docs/adr/0038-reading-scale-tickets-with-ai.md)), record the sale (prefilled from the photo), match it with the bank statement (CSV or Excel, [ADR 0039](../../docs/adr/0039-bank-statement-matching.md)) or by hand, and read each sale's settlement report |
| Certificados | Preview and issue a host's or site's monthly certificate, with its PDF; a host's monthly report (opt-in, emails, last reports), its goals and its sites', and the UI GreenMetric workbook ([ADR 0046](../../docs/adr/0046-host-monthly-report-goals-and-rankings.md)) |
| Comercios | Name merchants with their campus, place, hours and what they sell, shown in "Dónde gastar" ([ADR 0041](../../docs/adr/0041-participant-timeline-impact-and-where-to-spend.md)); settle or refund their redemptions of ZYR for pesos; export a merchant's movements for a range of days as Excel or CSV ([ADR 0045](../../docs/adr/0045-merchant-accounting-export.md)) |
| Sedes | Create hosts and set their payout address; create sites and set their hours |
| Precios | Centros de acopio ([ADR 0037](../../docs/adr/0037-prices-per-collection-center.md)): each center, its price per material with the suggested median of its sales, and the sites that sell to it; then the general reference prices |
| Operadores | Admins only: add, rename, promote, demote or deactivate operators |

## Wallet

Visitors get an embedded wallet: a key generated in the browser and kept in `localStorage`, so the
flow works without installing anything (testnet only). From the wallet menu they can switch to
MetaMask or Core instead, and add ZyrcleChain to it. Either way the API session comes from a
Sign-In with Ethereum signature ([`packages/client/src/siwe.ts`](../../packages/client/src/siwe.ts)), made only when a page needs
it, and cached for the tab.

ZYR is the L1's native coin and 1 ZYR = 1 COP, so balances and payments are shown in pesos.

## QR scanning

[`@yudiel/react-qr-scanner`](https://github.com/yudielcurbelo/react-qr-scanner) with its ZXing
WebAssembly decoder served from this origin (by default it is fetched from a CDN). The CSP in
[`security-headers.conf`](security-headers.conf) allows `'wasm-unsafe-eval'` for it and the camera
only for this origin.

## Run locally

The full stack on your machine, with anvil standing in for ZyrcleChain:

```bash
# 1. Database and broker, then the API's dependencies (see apps/api/README.md)
cd apps/api && docker compose -f dev/compose.yml up -d && .venv/bin/alembic upgrade head

# 2. A local chain with the Treasury deployed and seeded
anvil --chain-id 20261121 &
.venv/bin/python dev/local_chain.py >> .env       # chain URL, Treasury, factory, key files

# 3. Simulated containers and the API (add to .env: ZYRCLE_SIWE_DOMAIN=localhost,
#    ZYRCLE_CORS_ORIGINS=http://localhost:8080, ZYRCLE_DEMO_SIMULATOR_URL=http://127.0.0.1:8090)
ZYRCLE_SIM_PASSWORD=dev-password .venv/bin/zyrcle-sim serve --keys-dir dev/.local/keys \
  --devices ctr-0001,ctr-0002,ctr-0003,ctr-0004 --control-host 127.0.0.1 &
.venv/bin/zyrcle-api demo seed --keys-dir dev/.local/keys --devices ctr-0001,ctr-0002,ctr-0003,ctr-0004
.venv/bin/zyrcle-api serve &

# 4. The web app
cd ../web && npm ci && cp .env.example .env    # fill VITE_TREASURY_ADDRESS from step 2
npm run dev                                       # http://localhost:8080
```

Build-time settings (`VITE_*`, defaults in [`src/lib/config.ts`](src/lib/config.ts)):
`VITE_API_URL`, `VITE_SIWE_DOMAIN`, `VITE_CHAIN_ID`, `VITE_RPC_URL`, `VITE_TREASURY_ADDRESS`,
`VITE_IPFS_GATEWAY` (its origin must also be in the CSP), and `VITE_SENTRY_DSN` with
`VITE_RELEASE` for error reports.

## Error reports

Sentry ([ADR 0033](../../docs/adr/0033-error-reports-and-uptime.md)), loaded only when
`VITE_SENTRY_DSN` is set, so a build without one carries none of its code
([`src/lib/errorReports.ts`](src/lib/errorReports.ts)). No user data, cookies, headers or bodies
leave the browser, and `scrubReport` from `@zyrcle/client` cleans the rest. The release workflow
passes the repository variable `SENTRY_DSN_WEB`; unset, reports are off.

## Checks

```bash
npm run typecheck      # tsc -p tsconfig.app.json --noEmit
npx eslint .
npm test               # vitest run
npm run coverage       # vitest run --coverage (lib/ and console/; shown in CI, no floor)
npm run build
```

Unit tests ([ADR 0031](../../docs/adr/0031-testing-and-the-pre-production-check.md)) cover the logic
behind the pages: the certificate check in the browser (tampered leaves, another root, a different
IPFS copy, a gateway that is down), Safe proposals (the same hash and signature as the backend, a
changed proposal refused) and the console's formatting. The SIWE message, QR parsing and token
expiry are tested in [`packages/client`](../../packages/client). The pages themselves run in a real
browser in [`e2e/`](../../e2e/README.md), on every push and pull request; those journeys do not go
through the nginx image, so a change to its configuration or security headers still needs a look at
the live site.

## Deploy

`Dockerfile` builds the static site into unprivileged nginx with the security headers. Images are
published by the release workflow, only for commits whose CI passed, and deployed by digest with
[`deploy/deploy.sh`](../../deploy)
([ADR 0032](../../docs/adr/0032-deploys-pinned-recorded-and-backed-up.md)).
