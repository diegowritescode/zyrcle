#!/usr/bin/env bash
# Builds the Android APK on this Mac instead of on EAS's cloud (docs/adr/0043): the same eas.json
# profile, the same EAS environment variables and the same signing key, which EAS keeps and hands to
# the build, so the APK installs over the one already on the phones. No cloud build is spent.
#
#   apps/mobile/scripts/build-apk.sh [profile]     # profile: preview (default) or development
#
# The APK lands in apps/mobile/dist-apk/, named after the profile and the commit. Toolchain (the same
# one the sibling project uses): Homebrew's openjdk@21 and android-commandlinetools, with
# platform-tools, platforms;android-36, build-tools;36.0.0 and the NDK. README, "Build the APK on
# the Mac".
set -euo pipefail

cd "$(dirname "$0")/.."
profile="${1:-preview}"
case "$profile" in
  preview | development) ;;
  *) echo "profile must be preview or development (production makes an .aab for Play Store)" >&2; exit 2 ;;
esac

# Gradle for Android does not run on the newest JDKs; 21 is the one it supports.
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
# app.config.ts: a 6 GB Gradle heap and two workers on this machine.
export ZYRCLE_LOCAL_BUILD=1

# Push needs Firebase's file. It is not in git, so the copy EAS's build makes of the repo lacks it:
# point at this one by its full path.
if [[ ! -f google-services.json ]]; then
  echo "apps/mobile/google-services.json is missing: without it the APK gets no push" >&2
  exit 1
fi
export GOOGLE_SERVICES_JSON="$PWD/google-services.json"

# An APK must say which commit it came from. EAS copies the files as they are on disk, so a change
# that is not committed would end up in an APK named after a commit that does not have it.
if [[ -n "$(git status --porcelain -- . ../../packages)" && "${ALLOW_DIRTY:-}" != "1" ]]; then
  echo "uncommitted changes in apps/mobile or packages/: commit them first (or ALLOW_DIRTY=1)" >&2
  exit 1
fi
sha="$(git rev-parse HEAD)"
mkdir -p dist-apk
apk="dist-apk/zyrcle-$profile-${sha:0:12}.apk"

npx --yes eas-cli@latest build --platform android --profile "$profile" --local --non-interactive \
  --output "$apk"

# Checks on the result, so a wrong APK never reaches a phone. Each tool's output is read whole
# first: `tool | grep -q` under pipefail fails when grep stops reading early.
tools="$(ls -d "$ANDROID_HOME"/build-tools/* | sort -V | tail -1)"

# The key Expo keeps, which signed the APKs already on the phones (ADR 0043). Android installs an
# update only with the same key; any other would force an uninstall, which erases the phone's key.
expected_key="0f3637b0ac3a7d122edc6c45d4527ce56fead9434835b555c745714f7ab4107d"
certs="$("$tools/apksigner" verify --print-certs "$apk")"
if [[ "$certs" != *"SHA-256 digest: $expected_key"* ]]; then
  echo "not signed with Expo's key ($expected_key): it would not install over the app" >&2
  exit 1
fi
resources="$("$tools/aapt2" dump resources "$apk")"
if [[ "$resources" != *"string/google_app_id"* ]]; then
  echo "no google_app_id in the APK: google-services.json did not reach the build, push would fail" >&2
  exit 1
fi
abis="$(unzip -Z1 "$apk" | awk -F/ '$1 == "lib" && NF > 2 {print $2}' | sort -u | tr '\n' ' ')"
if [[ "$abis" != "arm64-v8a armeabi-v7a " ]]; then
  echo "native code for '$abis', expected only arm64-v8a and armeabi-v7a (ADR 0015)" >&2
  exit 1
fi
echo
echo "APK:          $apk ($(du -h "$apk" | cut -f1))"
echo "Commit:       $sha"
echo "Processors:   $abis"
echo "Signed with:  Expo's key, $expected_key"
