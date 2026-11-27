import * as Sentry from "@sentry/react-native";
import { scrubReport } from "@zyrcle/client";
import * as Application from "expo-application";
import Constants from "expo-constants";
import { SENTRY_DSN } from "./config";

/**
 * Error reports to Sentry without personal data (docs/adr/0033). Off without a DSN. Runs before the
 * app renders, so a crash on start is reported too.
 */
/** Report an error the app handled but someone should know about. Nothing without a DSN. */
export function reportError(error: Error): void {
  if (SENTRY_DSN) Sentry.captureException(error);
}

export function startErrorReports(): boolean {
  if (!SENTRY_DSN) return false;
  Sentry.init({
    dsn: SENTRY_DSN,
    release: `zyrcle@${Constants.expoConfig?.version ?? "dev"}`,
    // The Android version code, one per build (ADR 0043, amendment): which APK sent the report.
    dist: Application.nativeBuildVersion ?? undefined,
    // Nothing about the person leaves the phone (this SDK still uses sendDefaultPii); scrubReport
    // cleans the rest.
    sendDefaultPii: false,
    beforeSend: (event) => scrubReport(event),
    beforeBreadcrumb: (crumb) => scrubReport(crumb),
  });
  return true;
}
