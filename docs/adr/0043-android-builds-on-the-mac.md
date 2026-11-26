# ADR 0043: Android builds run on Diego's Mac, with EAS's own runner and Expo's signing key

- Status: proposed (2026-11-25)
- Decided by: Diego decided to build the APKs on his Mac on 2026-11-25, reusing what his other
  project already does there: "quiero que compilemos nuestros propios apks aqui en la mac, ya lo hago
  para aicfes, que es mi otro proyecto, entonces ve si podemos reutilizar ese sistema". Claude chose
  how (EAS's runner on the Mac rather than calling Gradle directly) and the checks.

## Context
ADR 0015 put the builds on Expo's cloud. The free plan allows a few Android builds a month and each
one waits in a queue for about 20 minutes, so every build needed Diego's approval (ADR 0022). Diego
now has a Mac that already builds his other Expo app: Java 21, Android's command-line tools, the
SDK and the NDK are installed, and that project calls `expo prebuild` and then Gradle, signing with
the debug key.

The debug key does not work for Zyrcle. Android installs an update only when it is signed with the
same key as the installed app, and the APKs already on the phones carry the key Expo keeps (SHA-256
`0f3637b0ac3a7d122edc6c45d4527ce56fead9434835b555c745714f7ab4107d`). An APK signed with another key
would force people to uninstall first, and uninstalling erases the phone's key (ADR 0010): each
person would go through the 48-hour recovery to get their account back. The debug key is also
public, so anyone could sign an "update" of Zyrcle with it.

## Decision
- **Builds run on the Mac with `eas build --local`**, through `apps/mobile/scripts/build-apk.sh`.
  It is the same build the cloud runs, on this machine: the same `eas.json` profile, the
  environment's variables from EAS, and the signing key Expo keeps, which EAS hands to the build
  for its duration. The key never lands in the repository or in a file Claude reads. No cloud build
  is spent.
- **The toolchain is the one the other project uses**: Homebrew's `openjdk@21` (Gradle for Android
  does not run on newer Java) and `android-commandlinetools`, with `platform-tools`,
  `platforms;android-36`, `build-tools;36.0.0` and the NDK. On this machine Gradle gets a 6 GB heap
  and two workers, set by `app.config.ts` only when the script runs (`ZYRCLE_LOCAL_BUILD=1`).
- **Firebase's file comes from the local copy.** `GOOGLE_SERVICES_JSON` is a secret EAS variable, and
  secret variables are readable only on EAS's servers. The script points the variable at
  `apps/mobile/google-services.json`, which stays out of git as before.
- **The script refuses a wrong APK.** It stops before building when `apps/mobile` or `packages/`
  have uncommitted changes, because the APK is named after the commit. After building it stops
  when the APK is not signed with Expo's key above, has no Firebase app ID (no push), or carries
  native code for anything but the two ARM families (ADR 0015).
- **The cloud build stays** for when the Mac is not available. It still spends the quota and still
  needs Diego's approval (ADR 0022). A build on the Mac spends nothing and needs no approval; giving
  an APK to people still goes through Diego.

## Consequences
- Builds no longer wait for a reason or a quota; a native change can be tried on a phone the same
  day. The first build on the Mac (2026-11-25, commit `d346b93` plus this change) took about 8
  minutes, 6 min 44 s of them in Gradle, and gave a 68 MB APK signed with Expo's key, with
  Firebase's app ID and ARM code only. The checks also passed on the last cloud APK and refused the
  same APK signed again with the debug key.
- Each build starts from a clean copy of the repository, so it compiles all the native code again.
  Gradle's downloads stay cached between builds.
- The build needs Diego's Mac and his Expo session (`eas login`): the signing key is still fetched
  from Expo. If Expo stopped serving it, `eas credentials` can download it once and the script can
  sign with it locally.
- EAS prints that `android.googleServicesFile` "is not checked in to your repository and won't be
  uploaded to the builder". That is true of the cloud; on the Mac the build reads the file at its
  full path, and the script's check confirms it reached the APK.
- Every `preview` APK so far has version code 1, the profile has no automatic increment. Android
  installs an APK with the same version code over the installed one, but neither the phone nor
  Sentry can tell two such builds apart. Raising the number per build is open.
- The Play Store's `.aab` (profile `production`) can be built the same way when the store comes
  (roadmap M7); the script accepts only `preview` and `development` until then.
