import * as Sentry from "@sentry/react";
import { scrubReport } from "@zyrcle/client";

/** Error reports to Sentry without personal data (docs/adr/0033). Loaded only when a DSN is set,
 * so a build without one carries none of this code. */
export function startErrorReports(dsn: string, release: string | undefined) {
    Sentry.init({
        dsn,
        release,
        environment: import.meta.env.MODE,
        sendDefaultPii: false,
        beforeSend: (event) => scrubReport(event),
        beforeBreadcrumb: (crumb) => scrubReport(crumb),
    });
}
