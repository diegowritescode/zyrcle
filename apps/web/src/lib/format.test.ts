import { describe, expect, it } from "vitest";
import { grams, kg, pesos, shortHex } from "./format";

describe("format", () => {
  it("shows ZYR as Colombian pesos", () => {
    expect(pesos(1500).replace(/\s/g, " ")).toMatch(/^\$ ?1\.500$/);
  });

  it("switches grams to kilos past 1 kg", () => {
    expect(grams(250)).toBe("250 g");
    expect(grams(1250)).toBe(kg(1.25, 2));
  });

  it("shortens addresses and hashes", () => {
    expect(shortHex("0x52908400098527886E0F7030069857D2E4169EE7")).toBe("0x5290…9EE7");
  });
});
