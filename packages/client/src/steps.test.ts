import { describe, expect, it } from "vitest";
import type { DepositStep, HistoryEntry } from "./api";
import { ago, monthLabel } from "./format";
import { currentStep, stepLine } from "./steps";

const step = (key: DepositStep["key"], status: DepositStep["status"], extra: Partial<DepositStep> = {}): DepositStep => ({
  key,
  status,
  at: null,
  amount_cop: null,
  share_cop: null,
  tx_hash: null,
  note: null,
  ...extra,
});

const entry = {
  id: "s1",
  container_id: "ctr-0001",
  container_name: "Contenedor PET",
  state: "verified",
  declared_material: "pet",
  tare_g: 0,
  deposited_g: 350,
  score: 1,
  reasons: [],
  close_reason: null,
  created_at: "2026-11-24T10:00:00Z",
  updated_at: "2026-11-24T10:00:00Z",
  payout: null,
} as HistoryEntry;

const nbsp = (s: string | null) => s?.replace(/\s/g, " ");

describe("deposit steps in Spanish", () => {
  it("says where the material went and who bought it", () => {
    expect(stepLine(step("deposited", "done"), entry)).toEqual({ title: "Depositado", detail: "350 g en Contenedor PET" });
    expect(stepLine(step("sold", "done", { note: "Centro de acopio La 80" }), entry).detail).toBe("A Centro de acopio La 80");
    expect(stepLine(step("sold", "pending"), entry).title).toBe("Esperando la venta");
  });

  it("explains a rejection, a review and a missing advance", () => {
    expect(stepLine(step("verified", "failed", { note: "No era PET" }), entry).detail).toBe("Motivo: No era PET");
    expect(stepLine(step("verified", "pending"), entry).title).toBe("En revisión");
    expect(stepLine(step("verified", "done", { note: "approved_after_review" }), entry).title).toBe("Aprobado tras revisión");
    expect(stepLine(step("advance", "skipped"), entry).title).toBe("Sin anticipo");
    expect(stepLine(step("advance", "pending", { note: "deferred", amount_cop: 90 }), entry).detail).toMatch(/tesorería/);
  });

  it("tells what the sale paid on top, or that the advance covered it", () => {
    const paid = stepLine(step("paid", "done", { amount_cop: 410, share_cop: 500 }), entry);
    expect(paid.title).toBe("Pagado");
    expect(nbsp(paid.detail)).toBe("$ 410 más, de una parte de $ 500");
    const covered = stepLine(step("paid", "done", { amount_cop: 0, share_cop: 80, note: "covered_by_advance" }), entry);
    expect(covered.title).toBe("Liquidado");
    expect(nbsp(covered.detail)).toBe("Tu parte fue $ 80; el anticipo ya la cubría.");
  });

  it("points at the furthest step reached, or the one that failed", () => {
    expect(currentStep([step("deposited", "done"), step("verified", "done"), step("advance", "pending")])?.key).toBe("verified");
    expect(currentStep([step("deposited", "done"), step("verified", "failed"), step("advance", "skipped")])?.key).toBe("verified");
    expect(currentStep([])).toBeNull();
  });
});

describe("dates for the impact and the collector", () => {
  it("names months and elapsed days", () => {
    expect(monthLabel("2026-11")).toBe("nov 2026");
    const now = new Date("2026-11-24T12:00:00Z");
    expect(ago("2026-11-24T08:00:00Z", now)).toBe("hoy");
    expect(ago("2026-11-23T08:00:00Z", now)).toBe("ayer");
    expect(ago("2026-11-14T08:00:00Z", now)).toBe("hace 10 días");
    expect(ago("2026-08-01T08:00:00Z", now)).toBe("hace 3 meses");
  });
});
