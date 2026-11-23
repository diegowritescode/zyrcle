import { hashTypedData, recoverTypedDataAddress, type Hex, type TypedDataDefinition } from "viem";

/** A Safe transaction on its way to two signatures, as `zyrcle-api safe propose` writes it
 * (docs/adr/0040, apps/api/src/zyrcle_api/multisig.py). */
export interface SafeProposal {
    safe: string;
    chain_id: number;
    to: string;
    data: string;
    nonce: number;
    description: string;
    value: number;
    operation: number;
    signatures: Record<string, string>;
    safe_tx_hash: string;
    typed_data: {
        types: Record<string, { name: string; type: string }[]>;
        primaryType: "SafeTx";
        domain: { chainId: number; verifyingContract: string };
        message: Record<string, string | number>;
    };
}

/** What viem needs: the types without EIP712Domain, which it derives from the domain. */
function definition(p: SafeProposal): TypedDataDefinition {
    const { EIP712Domain: _domain, ...types } = p.typed_data.types;
    return {
        domain: { chainId: p.typed_data.domain.chainId, verifyingContract: p.typed_data.domain.verifyingContract as Hex },
        types,
        primaryType: "SafeTx",
        message: p.typed_data.message,
    } as unknown as TypedDataDefinition;
}

/** Parse a proposal and check it was not changed after it was made. */
export function readProposal(text: string): SafeProposal {
    let p: SafeProposal;
    try {
        p = JSON.parse(text);
    } catch {
        throw new Error("Eso no es una propuesta: no es JSON.");
    }
    if (!p.typed_data || !p.safe_tx_hash) throw new Error("Eso no es una propuesta del Safe.");
    const m = p.typed_data.message;
    if (
        String(m.to).toLowerCase() !== p.to.toLowerCase() ||
        String(m.data).toLowerCase() !== p.data.toLowerCase() ||
        Number(m.nonce) !== p.nonce ||
        Number(m.operation) !== p.operation ||
        p.typed_data.domain.verifyingContract.toLowerCase() !== p.safe.toLowerCase() ||
        p.typed_data.domain.chainId !== p.chain_id
    ) {
        throw new Error("La propuesta fue modificada: sus partes no coinciden.");
    }
    if (hashTypedData(definition(p)) !== p.safe_tx_hash) throw new Error("La propuesta fue modificada: su huella no coincide.");
    return p;
}

/** Who made each signature; `null` when it is not over this proposal. */
export async function signersOf(p: SafeProposal): Promise<{ claimed: string; actual: string | null }[]> {
    return Promise.all(
        Object.entries(p.signatures).map(async ([claimed, signature]) => {
            try {
                const actual = await recoverTypedDataAddress({ ...definition(p), signature: signature as Hex });
                return { claimed, actual };
            } catch {
                return { claimed, actual: null };
            }
        }),
    );
}

export async function withSignature(p: SafeProposal, signature: string): Promise<{ proposal: SafeProposal; signer: string }> {
    const signer = await recoverTypedDataAddress({ ...definition(p), signature: signature as Hex });
    return { proposal: { ...p, signatures: { ...p.signatures, [signer]: signature } }, signer };
}
