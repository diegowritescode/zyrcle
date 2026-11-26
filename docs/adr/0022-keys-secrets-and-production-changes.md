# ADR 0022: Keys, secrets, and who may change production

- Status: accepted (2026-11-22), recorded 2026-11-22
- Decided by: Diego set the rules; Claude follows them.

## Context
The system holds keys that can mint ZYR (Treasury roles), take over accounts (the AccountFactory
guardian) or run the chain (P-Chain and L1 admin keys), plus API keys (Resend, Expo, Firebase).
Work is done with an AI assistant that has shell access to the VPS.

## Decision
- **Private keys live only on the VPS** (`~/.avalanche-cli/key`, files `0600` owned by the deploy
  user) and in Diego's offline operations inventory, which is never shown in chats or committed.
- **API keys are placed by Diego himself over SSH** (for example `RESEND_API_KEY` in
  `deploy/.env`); they never pass through the chat. Firebase files and the FCM service-account key
  stay in Diego's private folder and in EAS (ADR 0015).
- `deploy/.env` exists only on the VPS and is never printed. The repository holds no secrets;
  `deploy/.env.example` shows names only.
- **Changes need Diego's explicit approval:** pushing, deploying, deleting, running contract
  transactions on Fuji, installing software on the VPS, and spending EAS builds.

## Consequences
- Deploys pause until Diego approves them, which is intended.
- Rotating a key is a manual runbook (`docs/infrastructure.md`).

## Amendments
- **2026-11-25, Claude (ADR 0043, proposed):** "spending EAS builds" means builds on Expo's
  cloud, which use the monthly quota. A build on Diego's Mac spends nothing and needs no approval;
  giving an APK to people still goes through Diego.
