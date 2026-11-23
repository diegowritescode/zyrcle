import { describe, expect, it } from "vitest";
import fixture from "./multisig.fixture.json";
import { readProposal, signersOf, withSignature } from "./multisig";

// The fixture was made and signed by the backend (multisig.py): both sides must agree on the hash.
describe("Safe proposals in the browser", () => {
    it("computes the same hash as the backend and recovers the backend's signature", async () => {
        const p = readProposal(JSON.stringify(fixture));
        expect(p.safe_tx_hash).toBe(fixture.safe_tx_hash);
        const [only] = await signersOf(p);
        expect(only.actual).toBe(only.claimed);
    });

    it("refuses a proposal changed after it was made", () => {
        const changed = { ...fixture, typed_data: { ...fixture.typed_data, message: { ...fixture.typed_data.message, nonce: 4 } }, nonce: 4 };
        expect(() => readProposal(JSON.stringify(changed))).toThrow(/huella/);
        expect(() => readProposal(JSON.stringify({ ...fixture, to: "0x0000000000000000000000000000000000000001" }))).toThrow(/no coinciden/);
        expect(() => readProposal("nope")).toThrow(/JSON/);
    });

    it("adds a signature under the address that made it", async () => {
        const p = readProposal(JSON.stringify(fixture));
        const existing = Object.values(p.signatures)[0];
        const { signer, proposal } = await withSignature({ ...p, signatures: {} }, existing);
        expect(proposal.signatures[signer]).toBe(existing);
    });
});
