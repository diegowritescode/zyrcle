# ADR 0015: Android builds with EAS, push through Firebase, ARM code only

- Status: accepted (2026-11-23; proposed 2026-11-22)
- Decided by: Claude proposed; Diego created the Expo and Firebase accounts and ran the first
  build. Diego confirmed it on 2026-11-23: "confirmo 0015, 0027, 0028 y 0029".

## Context
Expo Go on Android cannot receive push from a server (ADR 0008), so payments and recovery warnings
need a real build. Diego has no Mac with Xcode or Android Studio, and the build must not depend on
this machine. The first build weighed 132 MB, and the app re-registered its push token in a loop.

## Decision
- **Builds run on Expo's cloud (EAS)** in the project `@diegowritescode/zyrcle`. The `preview`
  profile makes an installable APK pointed at production, for testing outside the Play Store.
  `production` is kept for the store.
- **Push goes through Firebase Cloud Messaging**, Firebase project `zyrcle-18c69`, app
  `xyz.deviego.zyrcle`. `google-services.json` is not in git: EAS receives it as the secret file
  variable `GOOGLE_SERVICES_JSON`, which `app.config.ts` reads. The FCM v1 service-account key lives
  only in Diego's private folder and in EAS credentials. Expo keeps the Android signing keystore.
- **ARM code only.** React Native packs native libraries for four processor families. The two x86
  families (emulators, Chromebooks) were 62 of the 132 MB. The build keeps `arm64-v8a` and
  `armeabi-v7a`; the 32-bit one stays because many low-cost phones still run a 32-bit Android. Set in
  `app.config.ts` (`reactNativeArchitectures`). The next build came out at 67 MB.
- **The push token is fetched once and re-sent only when Android changes it.** expo-notifications
  fires its token listeners on every native token fetch, same token included, so fetching from the
  listener looped (about ten registrations a second, which also slowed every other request).
- **Builds are spent on purpose.** The free plan has a monthly quota and a build takes about 20
  minutes, so builds wait for a reason (a native change, or a release to test on phones). Meanwhile
  the app is tested in Expo Go, which shows everything except server push.

## Consequences
- Testing push needs an installed build; Expo Go shows everything else.
- No x86 emulator can install these APKs. Add `x86_64` to the list for a build meant for one.
- The Play Store will need an `.aab` from the `production` profile, a privacy policy and the data
  safety form (roadmap M7).

## Amendments
- **2026-11-25, Diego decided to build on his Mac** ("quiero que compilemos nuestros propios apks
  aqui en la mac"): builds run on the Mac with `eas build --local`, same profiles, same variables and
  the same key Expo keeps (ADR 0043). The cloud build remains for when the Mac is not available.
