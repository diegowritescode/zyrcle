import { describe, expect, it } from "vitest";
import { anchorData, certificateRoot } from "./certificate";

// Values computed by the backend (apps/api/src/zyrcle_api/domain/impact.py) for the same leaves.
const leaves = [
  { deposit_id: "3f1c2b8e-0000-4000-8000-000000000001", material: "pet", grams: 100 },
  { deposit_id: "3f1c2b8e-0000-4000-8000-000000000002", material: "hdpe", grams: 250 },
  { deposit_id: "3f1c2b8e-0000-4000-8000-000000000003", material: "pet", grams: 75 },
];

describe("certificate verification", () => {
  it("rebuilds the backend's root, in any order", async () => {
    expect(await certificateRoot(leaves)).toBe("0x5b33cea3177b9b299d50cab6e2f1d9dd02f64c64041da2b6d29a01aaa7e558ad");
    expect(await certificateRoot([...leaves].reverse())).toBe("0x5b33cea3177b9b299d50cab6e2f1d9dd02f64c64041da2b6d29a01aaa7e558ad");
    expect(await certificateRoot([{ ...leaves[0], grams: 101 }, leaves[1], leaves[2]])).not.toBe("0x5b33cea3177b9b299d50cab6e2f1d9dd02f64c64041da2b6d29a01aaa7e558ad");
  });
  it("builds the anchor transaction's data", () => {
    expect(anchorData("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "0x5b33cea3177b9b299d50cab6e2f1d9dd02f64c64041da2b6d29a01aaa7e558ad")).toBe("0x5a5952434c452d434552542d31aaaaaaaabbbb4ccc8dddeeeeeeeeeeee5b33cea3177b9b299d50cab6e2f1d9dd02f64c64041da2b6d29a01aaa7e558ad");
  });
});
