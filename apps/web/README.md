# Zyrcle web app

The hackathon's interface (May 2025), kept as it was designed (eco palette, shadcn/ui components,
landing, the dashboard) and wired to the rebuilt backend in [`apps/api`](../api). Live at
https://zyrcle.deviego.xyz.

| Route | What it shows | Data |
|---|---|---|
| `/` | Landing | Live totals from `GET /v1/stats` instead of the hackathon's made-up figures |
| `/recycling` | The resident's deposit: scan the container's QR (camera or typed code), choose the material, live weight, "Terminé", verdict and payment; plus the resident's history | SIWE sign-in, `POST /v1/sessions`, WebSocket `/v1/sessions/{id}/live`, `GET /v1/me` |
| `/sites` | A host's dashboard across its sites, or one site's: totals, kilos per day and material, pesos paid per day, each site's numbers or each container's fill level and weight. `/residence` redirects here | `GET /v1/hosts/{id}/dashboard`, `GET /v1/sites/{id}/dashboard` |
| `/console` | Operations console ([ADR 0014](../../docs/adr/0014-operator-accounts.md)): sign-in by email code, review queue, incidents, collectors and printable bag labels, sales with the bank match and settlement report, hosts and sites, prices, operators | `/v1/operator/*` |
| `/certificates/:id` | A host's impact certificate ([ADR 0027](../../docs/adr/0027-impact-certificates.md)): totals per material, CO2e avoided, print view, CSV of the deposits, and "Verificar", which recomputes the root in the browser and compares it with the anchor transaction on ZyrcleChain | `GET /v1/certificates/{id}`, the public RPC |
| `/container/:id` | A container's screen, simulated: the QR whose code rotates every 30 s | `GET /v1/demo/containers` |
| `/collectors`, `/validator`, `/marketplace`, `/my-certificates` | What comes next (phase 4 and later) | none |

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
.venv/bin/python dev/local_chain.py >> .env       # ZYRCLE_CHAIN_RPC_URL, TREASURY, ORACLE key

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

## Checks

```bash
npm run typecheck && npx eslint . && npm test && npm run build
```

Unit tests cover the SIWE message (the same literal is parsed by the API's tests), QR parsing,
formatting and token expiry. The full flow (sign in, scan through a fake camera, deposit, payment
on chain, dashboard) was exercised with Playwright against the production nginx image and its CSP.

## Deploy

`Dockerfile` builds the static site into unprivileged nginx with the security headers. Images are
published by the release workflow and deployed with [`deploy/deploy.sh`](../../deploy).
