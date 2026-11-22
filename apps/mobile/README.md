# Zyrcle mobile app

The resident app (phase 3, [ADR 0006](../../docs/adr/0006-expo-mobile.md)): Expo SDK 58, React
Native 0.88, Expo Router. Same palette and components style as the web app, same API and the same
SIWE message through [`@zyrcle/client`](../../packages/client).

| Screen | What it does |
|---|---|
| Inicio | Balance in pesos, the next turn, a banner to go back to a deposit left open, "Reciclar ahora", how it works, last deposits, demo totals |
| Turnos | Book an hour at a container (up to 7 days ahead), see and cancel your turns ([ADR 0009](../../docs/adr/0009-time-slots.md)) |
| Escanear | Camera QR scanning (`expo-camera`), typed code fallback, the demo's simulated containers |
| Reciclar | Choose the material, open the lid, live weight over the WebSocket, "Terminé", verdict and the advance paid on chain |
| Depósitos | The resident's last 20 deposits and their payments |
| Cuenta | The wallet address, notifications, network, links, and (testnet) a new wallet |

## Wallet

A key generated on the phone (`expo-crypto` randomness, viem) and kept in the OS keychain or
keystore through `expo-secure-store`, readable only while the phone is unlocked and never copied
to another device. The resident never sees a seed phrase. Signing in is silent: the app signs the
SIWE message with the local key. Key recovery needs its own design before a real launch.

## Notifications

[ADR 0008](../../docs/adr/0008-push-notifications.md). The API pushes payments and deposit reviews
through Expo's push service; the app schedules the reminder 10 minutes before each turn on the
phone itself. Permission is asked in context (after booking a turn, or from Inicio or Cuenta), and
Android gets one channel per kind (Pagos, Depósitos en revisión, Recordatorios de turno).

Reminders work in Expo Go. Push does not on Android (Expo Go dropped it in SDK 53): it needs a
development build, made once with EAS:

1. `npx eas-cli@latest login`, then `npx eas-cli@latest init` in this folder. It links the project
   to your Expo account and writes `extra.eas.projectId` to `app.json` (commit that change).
2. In the [Firebase console](https://console.firebase.google.com), create a project and add an
   Android app with the package `xyz.deviego.zyrcle`. Download `google-services.json` and keep it
   out of git (it is in `.gitignore`). Hand it to EAS as a secret file:
   `npx eas-cli@latest env:set --name GOOGLE_SERVICES_JSON --type file --value ./google-services.json --visibility secret --environment development --environment preview --environment production`
3. Firebase, Project settings, Service accounts: generate a private key (JSON). Upload it with
   `npx eas-cli@latest credentials` (Android, Google Service Account, "for Push Notifications (FCM
   V1)"), then delete the local copy.
4. `npx eas-cli@latest build --profile development --platform android`, install the APK from the
   link it prints, and run `npx expo start` as usual: the development build replaces Expo Go.

iOS needs an Apple Developer account; `eas build` creates the push key when asked.

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
Native builds go through EAS (`eas build`, profiles in `eas.json`); there are no `ios/` or
`android/` folders in the repo. Booking a turn, the home card and being sent to Turnos when a
container is closed were exercised the same way.
