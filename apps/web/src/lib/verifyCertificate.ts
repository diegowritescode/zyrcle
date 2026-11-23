import { certificateRoot, parseAnchor, type Certificate, type CertificateDocument } from "@zyrcle/client";

export type Check = { state: "idle" | "checking" | "ok" | "bad"; detail?: string };

export interface Sources {
    /** ZyrcleChain's public RPC. */
    rpcUrl: string;
    /** An IPFS gateway, `…/ipfs/`. */
    ipfsGateway: string;
    /** For tests. */
    fetch?: typeof fetch;
}

const short = (h: string) => `${h.slice(0, 10)}…`;

/**
 * Check a certificate in the browser (ADR 0027 and its amendment). Recompute the root from the
 * published leaves and compare it with the anchor transaction read from the chain. When the anchor
 * names an IPFS copy, read that copy by the CID written on chain, not the one our server reports,
 * and check that its own leaves give the anchored root too.
 */
export async function verifyCertificate(c: Certificate, sources: Sources): Promise<Check> {
    const get = sources.fetch ?? fetch;
    const root = await certificateRoot(c.leaves ?? []);
    if (root !== c.merkle_root) return { state: "bad", detail: "Las hojas publicadas no dan la raíz del certificado." };
    if (!c.anchor_tx) return { state: "bad", detail: "El certificado aún no está anclado en la cadena." };
    const res = await get(sources.rpcUrl, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_getTransactionByHash", params: [c.anchor_tx] }),
    });
    const tx = (await res.json()).result;
    if (!tx) return { state: "bad", detail: "No encontramos la transacción de anclaje en ZyrcleChain." };
    const anchor = parseAnchor(String(tx.input));
    if (!anchor || anchor.certificateId !== c.id || anchor.root !== root) return { state: "bad", detail: "La transacción ancla otra raíz." };
    const onChain = `Raíz ${short(root)} anclada en la transacción ${short(c.anchor_tx)}`;
    if (!anchor.cid) return { state: "ok", detail: `${onChain}.` };
    if (anchor.cid !== c.ipfs_cid) return { state: "bad", detail: "La copia en IPFS que nombra la cadena no es la que muestra esta página." };
    let copy: CertificateDocument;
    try {
        const r = await get(`${sources.ipfsGateway.replace(/\/?$/, "/")}${anchor.cid}`);
        if (!r.ok) throw new Error(String(r.status));
        copy = await r.json();
    } catch {
        return { state: "ok", detail: `${onChain}. No pudimos abrir la copia en IPFS en este momento; inténtalo más tarde.` };
    }
    if (copy.id !== c.id || (await certificateRoot(copy.leaves ?? [])) !== root) {
        return { state: "bad", detail: "La copia en IPFS no da la raíz anclada." };
    }
    return { state: "ok", detail: `${onChain}, y la copia permanente en IPFS da la misma raíz.` };
}
