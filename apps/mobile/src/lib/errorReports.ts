import * as Sentry from "@sentry/react-native";
import { scrubReport } from "@zyrcle/client";
import Constants from "expo-constants";
import { SENTRY_DSN } from "./config";

/**
 * Error reports to Sentry without personal data (docs/adr/0033). Off without a DSN. Runs before the
 * app renders, so a crash on start is reported too.
 */
export function startErrorReports(): boolean {
  if (!SENTRY_DSN) return false;
  Sentry.init({
    dsn: SENTRY_DSN,
    release: `zyrcle@${Constants.expoConfig?.version ?? "dev"}`,
    // Nothing about the person leaves the phone (this SDK still uses sendDefaultPii); scrubReport
    // cleans the rest.
    sendDefaultPii: false,
    beforeSend: (event) => scrubReport(event),
    beforeBreadcrumb: (crumb) => scrubReport(crumb),
  });
  return true;
}
