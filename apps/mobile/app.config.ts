/**
 * What app.json cannot say on its own:
 * - Firebase's google-services.json, which Android push needs and which must not live in git. EAS
 *   builds receive it as the file environment variable GOOGLE_SERVICES_JSON (README,
 *   "Notifications"); a build on the Mac (scripts/build-apk.sh) points it at the local copy.
 * - Native code for phones only. React Native packs its native libraries for four processor
 *   families, and the x86 pair (emulators, Chromebooks) was 62 of the first APK's 132 MB. 32-bit
 *   ARM stays: many low-cost phones still run a 32-bit Android.
 * - On the Mac (ZYRCLE_LOCAL_BUILD=1, set by scripts/build-apk.sh), a bigger Gradle heap and two
 *   workers: the C++ of reanimated and worklets, four at a time with the default 2 GB heap, killed
 *   the same build in the sibling project (exit 137). EAS's cloud machines keep the defaults.
 */
import type { ConfigContext, ExpoConfig } from "expo/config";
import { withGradleProperties } from "expo/config-plugins";

const ANDROID_ARCHITECTURES = "armeabi-v7a,arm64-v8a";
const LOCAL_BUILD_GRADLE: Record<string, string> = {
  "org.gradle.jvmargs": "-Xmx6144m -XX:MaxMetaspaceSize=1536m",
  "org.gradle.workers.max": "2",
};

export default ({ config }: ConfigContext): ExpoConfig => {
  const googleServicesFile = process.env.GOOGLE_SERVICES_JSON;
  const base: ExpoConfig = {
    ...(config as ExpoConfig),
    android: { ...config.android, ...(googleServicesFile ? { googleServicesFile } : {}) },
  };
  const properties: Record<string, string> = {
    reactNativeArchitectures: ANDROID_ARCHITECTURES,
    ...(process.env.ZYRCLE_LOCAL_BUILD === "1" ? LOCAL_BUILD_GRADLE : {}),
  };
  return withGradleProperties(base, (gradle) => {
    gradle.modResults = gradle.modResults.filter((p) => !(p.type === "property" && p.key in properties));
    for (const [key, value] of Object.entries(properties)) {
      gradle.modResults.push({ type: "property", key, value });
    }
    return gradle;
  });
};
