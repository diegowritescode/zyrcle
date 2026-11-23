import { describe, expect, it } from "vitest";
import { anchorData, certificateRoot, type Certificate } from "@zyrcle/client";
import { verifyCertificate } from "./verifyCertificate";

const ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
const CID = "bafkreigh2akiscaildcqabsyg3dfr6chu3fgpregiymsck7e7aqa4s52zy";
const TX = "0x" + "ab".repeat(32);
const leaves = [
    { deposit_id: "3f1c2b8e-0000-4000-8000-000000000001", material: "pet", grams: 100 },
    { deposit_id: "3f1c2b8e-0000-4000-8000-000000000002", material: "hdpe", grams: 250 },
];

async function certificate(over: Partial<Certificate> = {}): Promise<Certificate> {
    return {
        id: ID,
        host: { id: "h", name: "Universidad", kind: "university" },
        site: null,
        period: "2026-11",
        factors_version: "warm-v16",
        deposits: 2,
        participants: 2,
        grams: 350,
        co2e_g: 331,
        by_material: {},
        merkle_root: await certificateRoot(leaves),
        status: "anchored",
        anchor_tx: TX,
        ipfs_cid: CID,
        ipfs_url: `https://gw/ipfs/${CID}`,
        issued_by: "x",
        created_at: "2026-11-23T00:00:00Z",
        anchored_at: "2026-11-23T00:01:00Z",
        leaves,
        ...over,
    } as Certificate;
}

/** A chain whose anchor carries `input`, and a gateway that serves `copy` (or fails). */
function world(input: string | null, copy: unknown | "down") {
    const fake = async (url: RequestInfo | URL) => {
        if (String(url) === "https://rpc") return new Response(JSON.stringify({ result: input === null ? null : { input } }));
        if (copy === "down") throw new TypeError("network");
        return new Response(JSON.stringify(copy), { status: String(url).endsWith(CID) ? 200 : 404 });
    };
    return { rpcUrl: "https://rpc", ipfsGateway: "https://gw/ipfs", fetch: fake as typeof fetch };
}

describe("verifying a certificate in the browser", () => {
    it("matches when the chain, the page and the IPFS copy agree", async () => {
        const c = await certificate();
        const check = await verifyCertificate(c, world(anchorData(ID, c.merkle_root, CID), { id: ID, leaves }));
        expect(check.state).toBe("ok");
        expect(check.detail).toMatch(/copia permanente en IPFS da la misma raíz/);
    });

    it("accepts an anchor from before the IPFS copy", async () => {
        const c = await certificate({ ipfs_cid: null, ipfs_url: null });
        expect((await verifyCertificate(c, world(anchorData(ID, c.merkle_root), "down"))).state).toBe("ok");
    });

    it("refuses a page whose leaves were changed", async () => {
        const c = await certificate({ leaves: [{ ...leaves[0], grams: 101 }, leaves[1]] });
        expect((await verifyCertificate(c, world(null, "down"))).detail).toMatch(/no dan la raíz/);
    });

    it("refuses an anchor of another root", async () => {
        const c = await certificate();
        const other = anchorData(ID, "0x" + "00".repeat(32), CID);
        expect((await verifyCertificate(c, world(other, { id: ID, leaves }))).detail).toMatch(/otra raíz/);
    });

    it("refuses when the server shows a different copy than the chain names", async () => {
        const c = await certificate({ ipfs_cid: "bafkreiotherotherotherotherotherotherotherotherotherother" });
        expect((await verifyCertificate(c, world(anchorData(ID, c.merkle_root, CID), { id: ID, leaves }))).detail).toMatch(/no es la que muestra/);
    });

    it("refuses an IPFS copy whose leaves do not give the anchored root", async () => {
        const c = await certificate();
        const tampered = { id: ID, leaves: [{ ...leaves[0], grams: 999 }, leaves[1]] };
        expect((await verifyCertificate(c, world(anchorData(ID, c.merkle_root, CID), tampered))).detail).toMatch(/no da la raíz anclada/);
    });

    it("still checks the chain when the gateway is down, and says so", async () => {
        const c = await certificate();
        const check = await verifyCertificate(c, world(anchorData(ID, c.merkle_root, CID), "down"));
        expect(check.state).toBe("ok");
        expect(check.detail).toMatch(/No pudimos abrir la copia en IPFS/);
    });

    it("refuses a certificate that is not anchored yet", async () => {
        const c = await certificate({ anchor_tx: null, status: "issued" });
        expect((await verifyCertificate(c, world(null, "down"))).detail).toMatch(/aún no está anclado/);
    });
});
