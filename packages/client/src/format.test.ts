import { describe, expect, it } from "vitest";
import { dayLabel, grams, hourLabel, kg, pesos, shortHex, slotLabel } from "./format";

describe("format", () => {
  it("shows ZYR as Colombian pesos", () => {
    expect(pesos(1500).replace(/\s/g, " ")).toMatch(/^\$ ?1\.500$/);
  });

  it("keeps small totals precise and large ones short", () => {
    expect(kg(0.84)).toBe("0,84 kg");
    expect(kg(1234.56)).toBe("1.234,6 kg");
  });

  it("switches grams to kilos past 1 kg", () => {
    expect(grams(250)).toBe("250 g");
    expect(grams(1250)).toBe(kg(1.25, 2));
  });

  it("shortens addresses and hashes", () => {
    expect(shortHex("0x52908400098527886E0F7030069857D2E4169EE7")).toBe("0x5290…9EE7");
  });

  it("says hours the Colombian way", () => {
    expect(hourLabel(0)).toBe("12:00 a. m.");
    expect(hourLabel(7)).toBe("7:00 a. m.");
    expect(hourLabel(12)).toBe("12:00 m.");
    expect(hourLabel(15)).toBe("3:00 p. m.");
    expect(slotLabel(23)).toBe("11:00 p. m. – 12:00 a. m.");
  });

  it("names nearby days", () => {
    expect(dayLabel("2026-11-22", "2026-11-22")).toBe("Hoy");
    expect(dayLabel("2026-11-23", "2026-11-22")).toBe("Mañana");
    expect(dayLabel("2026-11-26", "2026-11-22")).toMatch(/^jue 26 nov$/);
  });
});
