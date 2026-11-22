/**
 * Adds what must not live in git to app.json: Firebase's google-services.json, which Android push
 * needs. EAS builds receive it as the file environment variable GOOGLE_SERVICES_JSON (README,
 * "Notifications"); a local native build sets GOOGLE_SERVICES_JSON=./google-services.json.
 */
import type { ConfigContext, ExpoConfig } from "expo/config";

export default ({ config }: ConfigContext): ExpoConfig => {
  const googleServicesFile = process.env.GOOGLE_SERVICES_JSON;
  return {
    ...(config as ExpoConfig),
    android: { ...config.android, ...(googleServicesFile ? { googleServicesFile } : {}) },
  };
};
