import { describe, expect, it } from "vitest";
import { containerQr, manualCode, parseContainerQr, parseManualCode } from "./qr";

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
