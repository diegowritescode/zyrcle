import { describe, expect, it } from "vitest";
import { bagQr, containerQr, manualCode, parseBagQr, parseContainerQr, parseManualCode } from "./qr";

describe("container QR", () => {
  it("round-trips what the container's screen shows", () => {
    const qr = containerQr("ctr-0001", "7KQ2MX");
    expect(qr).toBe("zyrcle://c/ctr-0001?code=7KQ2MX");
    expect(parseContainerQr(qr)).toEqual({ containerId: "ctr-0001", code: "7KQ2MX" });
  });

  it("rejects anything that is not a Zyrcle container code", () => {
    for (const raw of [
      "https://example.com",
      "zyrcle://c/ctr-0001",
      "zyrcle://c/../admin?code=AAAAAA",
      "zyrcle://c/ctr-0001?code=abc def",
      "",
    ]) {
      expect(parseContainerQr(raw)).toBeNull();
    }
  });

  it("reads the code typed by hand, case-insensitively", () => {
    expect(manualCode("ctr-0002", "AB12CD")).toBe("ctr-0002 AB12CD");
    expect(parseManualCode("  CTR-0002   ab12cd ")).toEqual({ containerId: "ctr-0002", code: "AB12CD" });
    expect(parseManualCode("ctr-0002")).toBeNull();
  });
});

describe("bag QR", () => {
  it("reads a printed label or a typed code", () => {
    expect(parseBagQr("zyrcle://b/7KQ2MXAB")).toBe("7KQ2MXAB");
    expect(parseBagQr(" 7kq2mxab ")).toBe("7KQ2MXAB");
    expect(parseBagQr(bagQr("0123ABCD"))).toBe("0123ABCD");
  });
  it("rejects anything else", () => {
    expect(parseBagQr("zyrcle://c/ctr-0001?code=7KQ2MX")).toBeNull();
    expect(parseBagQr("7KQ2MXA")).toBeNull(); // too short
    expect(parseBagQr("ILOU1234")).toBeNull(); // not Crockford
  });
});
