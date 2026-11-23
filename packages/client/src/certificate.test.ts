import { describe, expect, it } from "vitest";
import { anchorData, certificateRoot, parseAnchor } from "./certificate";

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
  it("adds the IPFS copy's CID, exactly as the backend does, and reads it back", () => {
    const id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
    const root = "0x5b33cea3177b9b299d50cab6e2f1d9dd02f64c64041da2b6d29a01aaa7e558ad";
    const cid = "bafkreigh2akiscaildcqabsyg3dfr6chu3fgpregiymsck7e7aqa4s52zy";
    const data = anchorData(id, root, cid);
    expect(data).toBe(
      "0x5a5952434c452d434552542d32aaaaaaaabbbb4ccc8dddeeeeeeeeeeee5b33cea3177b9b299d50cab6e2f1d9dd02f64c64041da2b6d29a01aaa7e558ad6261666b726569676832616b69736361696c646371616273796733646672366368753366677072656769796d73636b376537617161347335327a79",
    );
    expect(parseAnchor(data)).toEqual({ certificateId: id, root, cid });
    expect(parseAnchor(anchorData(id, root))).toEqual({ certificateId: id, root, cid: null });
    expect(parseAnchor("0x1234")).toBeNull();
    expect(parseAnchor(anchorData(id, root) + "00")).toBeNull();
  });
});
