# Zyrcle mobile app

The resident app (phase 3, [ADR 0006](../../docs/adr/0006-expo-mobile.md)): Expo SDK 58, React
Native 0.88, Expo Router. Same palette and components style as the web app, same API and the same
SIWE message through [`@zyrcle/client`](../../packages/client).

| Screen | What it does |
|---|---|
| Inicio | Balance in pesos, a banner to go back to a deposit left open, "Reciclar ahora", how it works, last deposits, demo totals |
| Escanear | Camera QR scanning (`expo-camera`), typed code fallback, the demo's simulated containers |
| Reciclar | Choose the material, open the lid, live weight over the WebSocket, "Terminé", verdict and the advance paid on chain |
| Depósitos | The resident's last 20 deposits and their payments |
| Cuenta | The wallet address, network, links, and (testnet) a new wallet |

## Wallet

A key generated on the phone (`expo-crypto` randomness, viem) and kept in the OS keychain or
keystore through `expo-secure-store`, readable only while the phone is unlocked and never copied
to another device. The resident never sees a seed phrase. Signing in is silent: the app signs the
SIWE message with the local key. Key recovery needs its own design before a real launch.

## Deep link

A container's QR is `zyrcle://c/<id>?code=<code>` and the app registers the `zyrcle` scheme, so in
an installed build the phone's own camera opens the app straight on that container
(`src/app/c/[containerId].tsx`). Expo Go does not register custom schemes; scan from inside the app.

## Try it on your phone

```bash
npm ci
npx expo start          # scan the QR with the camera (iOS) or the Expo Go app (Android)
```

The phone and the computer must be on the same network (or use `npx expo start --tunnel`). The app
talks to the public testnet API by default. Open a container's screen on the computer,
https://zyrcle.deviego.xyz/container/ctr-0001, and scan it from "Reciclar ahora".

Point it at a local stack with `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_RPC_URL` and
`EXPO_PUBLIC_SIWE_DOMAIN` (see [apps/web/README.md](../web/README.md) for running the stack).

## Checks

```bash
npm run typecheck && npx expo lint && npx expo export --platform ios --platform android
```

The full flow (camera scan, deposit, payment, history) was exercised with Playwright on the app's
web build at phone size, against a local stack with a fake camera showing a live container QR.
Native builds go through EAS (`eas build`); there are no `ios/` or `android/` folders in the repo.
