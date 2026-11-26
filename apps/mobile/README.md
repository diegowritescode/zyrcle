# Zyrcle mobile app

The resident and collector app (phase 3, [ADR 0006](../../docs/adr/0006-expo-mobile.md)): Expo SDK 58, React
Native 0.88, Expo Router. Same palette and components style as the web app, same API and the same
SIWE message through [`@zyrcle/client`](../../packages/client).

| Screen | What it does |
|---|---|
| Inicio | The data-policy consent until accepted ([ADR 0028](../../docs/adr/0028-pilot-readiness.md)), balance in pesos, the next turn, a banner to go back to a deposit left open, "Reciclar ahora", how it works, last deposits, demo totals |
| Turnos | Book an hour at a container (up to 7 days ahead), see and cancel your turns ([ADR 0009](../../docs/adr/0009-time-slots.md)) |
| Escanear | Camera QR scanning (`expo-camera`), typed code fallback, the demo's simulated containers |
| Reciclar | Choose the material, open the lid, live weight over the WebSocket, "Terminé", verdict and the advance paid on chain |
| Depósitos | The resident's last 20 deposits and their payments: the advance, plus what each got when its bag was sold ([ADR 0013](../../docs/adr/0013-sale-and-settlement.md)); tap one for its steps up to the settlement; "Mi impacto" ([ADR 0041](../../docs/adr/0041-participant-timeline-impact-and-where-to-spend.md)) |
| Dónde gastar | The campus merchants that take ZYR, with place, hours and what they sell (`/spend`, [ADR 0041](../../docs/adr/0041-participant-timeline-impact-and-where-to-spend.md)). Reached from Depósitos |
| Cuenta | The account address, the recovery email, "¿Perdiste tu teléfono anterior?", notifications, network, links, and (testnet) a new account |
| Recolección | For collectors only ([ADR 0012](../../docs/adr/0012-collection-and-bags.md)): open a container, scan a bag, take one material out while the container's scale weighs it, residue, close; seal full bags; the containers fullest first and what each collection paid ([ADR 0042](../../docs/adr/0042-collector-fill-alerts-and-earnings.md)). Reached from Cuenta |
| Pagar | Pay a campus merchant's QR from the account: the phone signs, the backend relays and pays the gas ([ADR 0029](../../docs/adr/0029-closed-loop-payments.md)). Reached from Escanear |
| Comercio | For merchants only: charge with a QR, see payments, and turn ZYR into pesos. Reached from Cuenta |
| Recuperar tu cuenta | Bring an older account to this phone with the code sent to its recovery email ([ADR 0010](../../docs/adr/0010-smart-accounts-and-recovery.md)) |

## Wallet and account

A key generated on the phone (`expo-crypto` randomness, viem) and kept in the OS keychain or
keystore through `expo-secure-store`, readable only while the phone is unlocked and never copied
to another device. The resident never sees a seed phrase. Signing in is silent: the app signs the
SIWE message with the local key.

The ZYR does not live at that key: it lives in the resident's smart account on ZyrcleChain, which
the key controls ([ADR 0010](../../docs/adr/0010-smart-accounts-and-recovery.md)). If the phone is
lost, the resident proves their recovery email on a new phone, the current phone is warned by push
and email, and after 48 hours the account obeys the new phone's key. The new phone cannot deposit
or book during the wait. A phone whose account moved away shows "Esta cuenta ya está en otro
teléfono" and can only start a new account.

Wallets from before smart accounts were paid to the key. After signing in, the app moves that
balance into the account, but only if `EXPO_PUBLIC_ACCOUNT_FACTORY` is set and the account the API
names is the one this key's address predicts (`predictAccount` in `src/lib/chain.ts`).

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

## Build the APK on the Mac

```bash
scripts/build-apk.sh            # preview, the installable APK pointed at production
scripts/build-apk.sh development
```

It runs EAS's own build on this machine (`eas build --local`,
[ADR 0043](../../docs/adr/0043-android-builds-on-the-mac.md)): the same profile, the EAS
environment's variables and the signing key Expo keeps, so the APK installs over the one already on
the phones. No cloud build is spent. It takes about 8 minutes and leaves
`dist-apk/zyrcle-<profile>-<commit>.apk`.

The script stops before building when `apps/mobile` or `packages/` have uncommitted changes, and
after building when the APK is not signed with Expo's key, lacks Firebase's app ID (no push) or
carries native code for anything but the two ARM families. An APK signed with any other key would
not install over the app, and uninstalling erases the phone's key: every account would go through
the 48-hour recovery.

What the Mac needs, all from Homebrew: `openjdk@21` (Gradle for Android does not run on newer
Java), `android-commandlinetools`, and from `sdkmanager` `platform-tools`, `platforms;android-36`,
`build-tools;36.0.0` and the NDK; `google-services.json` in this folder; and an open Expo session
(`npx eas-cli@latest whoami`). EAS's warning that `android.googleServicesFile` "won't be uploaded to
the builder" is about the cloud; on the Mac the build reads the file from its full path.

Only EAS variables with visibility plain text or sensitive reach a build on the Mac. Secret ones are
readable only on EAS's servers.

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
`EXPO_PUBLIC_SIWE_DOMAIN` (see [apps/web/README.md](../web/README.md) for running the stack). The
other build-time settings, with their defaults in [`src/lib/config.ts`](src/lib/config.ts), are
`EXPO_PUBLIC_CHAIN_ID`, `EXPO_PUBLIC_ACCOUNT_FACTORY`, `EXPO_PUBLIC_WEB_URL` and
`EXPO_PUBLIC_SENTRY_DSN`.

## Error reports

Sentry (`@sentry/react-native`, [ADR 0033](../../docs/adr/0033-error-reports-and-uptime.md)),
started by `startErrorReports` in [`src/lib/errorReports.ts`](src/lib/errorReports.ts) before the
app renders, so a crash on start is reported too. It is off unless `EXPO_PUBLIC_SENTRY_DSN` is set,
as an EAS environment variable with visibility sensitive (builds on the Mac cannot read secret ones). The value is read at build time, so reports start with the first
build made after it is set. No personal data is sent (`sendDefaultPii: false`), and `scrubReport`
from `@zyrcle/client` cleans every event and breadcrumb.

## Checks

```bash
npm run typecheck && npx expo lint && npm test && npx expo export --platform ios --platform android
```

`npm test` runs Vitest ([`src/lib/notifications.test.ts`](src/lib/notifications.test.ts), ADR 0031)
with the native modules replaced by stand-ins: the push token is registered once, again only when
Android hands over a different token, and after a failed attempt (the loop of the first APK); turn
reminders are scheduled before each turn and cancelled when the booking is gone.

The screens run in a real browser in [`e2e/`](../../e2e/README.md) on the app's web export, on
every push and pull request: a collection from the phone, a payment to a merchant, and a lost
phone's recovery. Native builds go through EAS (`scripts/build-apk.sh` on the Mac, profiles in `eas.json`); there are no
`ios/` or `android/` folders in the repo.
