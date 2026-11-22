/**
 * What app.json cannot say on its own:
 * - Firebase's google-services.json, which Android push needs and which must not live in git. EAS
 *   builds receive it as the file environment variable GOOGLE_SERVICES_JSON (README,
 *   "Notifications"); a local native build sets GOOGLE_SERVICES_JSON=./google-services.json.
 * - Native code for phones only. React Native packs its native libraries for four processor
 *   families, and the x86 pair (emulators, Chromebooks) was 62 of the first APK's 132 MB. 32-bit
 *   ARM stays: many low-cost phones still run a 32-bit Android.
 */
import type { ConfigContext, ExpoConfig } from "expo/config";
import { withGradleProperties } from "expo/config-plugins";

const ANDROID_ARCHITECTURES = "armeabi-v7a,arm64-v8a";

export default ({ config }: ConfigContext): ExpoConfig => {
  const googleServicesFile = process.env.GOOGLE_SERVICES_JSON;
  const base: ExpoConfig = {
    ...(config as ExpoConfig),
    android: { ...config.android, ...(googleServicesFile ? { googleServicesFile } : {}) },
  };
  return withGradleProperties(base, (gradle) => {
    const key = "reactNativeArchitectures";
    gradle.modResults = gradle.modResults.filter((p) => !(p.type === "property" && p.key === key));
    gradle.modResults.push({ type: "property", key, value: ANDROID_ARCHITECTURES });
    return gradle;
  });
};
