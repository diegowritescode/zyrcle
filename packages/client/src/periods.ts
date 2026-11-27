import type { Period } from "./api";

/** A ready-made range for the merchant's export (docs/adr/0045). */
export interface NamedPeriod extends Period {
  label: string;
}

/** The API reads export dates as days in Bogotá (its `ZYRCLE_TIMEZONE`), so "today" is Bogotá's
 * too, whatever the device's clock zone says. */
export const EXPORT_TIME_ZONE = "America/Bogota";

const iso = (y: number, m: number, d: number) => new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10);

/** Year, month (1 to 12) and day of `now` in `timeZone`. */
function dayIn(now: Date, timeZone: string): [number, number, number] {
  try {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone, year: "numeric", month: "numeric", day: "numeric" }).formatToParts(now);
    const part = (type: string) => Number(parts.find((p) => p.type === type)?.value);
    const ymd: [number, number, number] = [part("year"), part("month"), part("day")];
    if (ymd.every(Number.isFinite)) return ymd;
  } catch {
    // An engine without time zone data: the device's own calendar, Bogotá's for Zyrcle's people.
  }
  return [now.getFullYear(), now.getMonth() + 1, now.getDate()];
}

/** This month so far, the whole last month, and this year so far. */
export function exportPeriods(now: Date, timeZone = EXPORT_TIME_ZONE): NamedPeriod[] {
  const [y, m, d] = dayIn(now, timeZone);
  const today = iso(y, m - 1, d);
  return [
    { label: "Este mes", start: iso(y, m - 1, 1), end: today },
    // Day 0 of a month is the last day of the one before.
    { label: "Mes pasado", start: iso(y, m - 2, 1), end: iso(y, m - 1, 0) },
    { label: "Este año", start: iso(y, 0, 1), end: today },
  ];
}
