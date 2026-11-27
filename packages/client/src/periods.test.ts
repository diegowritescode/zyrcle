import { describe, expect, it } from "vitest";
import { exportQuery } from "./api";
import { exportPeriods } from "./periods";

// Noon in Bogotá (UTC-5) is 17:00 UTC.
const bogota = (y: number, m: number, d: number, h = 12) => new Date(Date.UTC(y, m - 1, d, h + 5));

describe("exportPeriods", () => {
  it("gives this month so far, the whole last month and this year so far", () => {
    expect(exportPeriods(bogota(2026, 11, 27))).toEqual([
      { label: "Este mes", start: "2026-11-01", end: "2026-11-27" },
      { label: "Mes pasado", start: "2026-10-01", end: "2026-10-31" },
      { label: "Este año", start: "2026-01-01", end: "2026-11-27" },
    ]);
  });

  it("counts days in Bogotá, not in the device's zone", () => {
    // 30 Nov at 21:00 in Bogotá is already 1 Dec in UTC.
    expect(exportPeriods(bogota(2026, 11, 30, 21))[0]).toMatchObject({ start: "2026-11-01", end: "2026-11-30" });
    expect(exportPeriods(bogota(2026, 11, 30, 21), "UTC")[0]).toMatchObject({ start: "2026-12-01", end: "2026-12-01" });
  });

  it("crosses into last year in January", () => {
    const [, last, year] = exportPeriods(bogota(2027, 1, 5));
    expect(last).toMatchObject({ start: "2026-12-01", end: "2026-12-31" });
    expect(year).toMatchObject({ start: "2027-01-01", end: "2027-01-05" });
  });

  it("knows February's length", () => {
    expect(exportPeriods(bogota(2028, 3, 1))[1]).toMatchObject({ start: "2028-02-01", end: "2028-02-29" });
  });
});

describe("exportQuery", () => {
  it("puts the range and the format in the query", () => {
    expect(exportQuery({ start: "2026-11-01", end: "2026-11-30" }, "xlsx")).toBe(
      "start=2026-11-01&end=2026-11-30&format=xlsx",
    );
  });
});
