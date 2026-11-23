/**
 * Verifying an impact certificate in the browser (docs/adr/0027): rebuild the Merkle root from the
 * published leaves and compare it with the data of the transaction that anchored it.
 * Mirrors apps/api/src/zyrcle_api/domain/impact.py.
 */
const PREFIX = "ZYRCLE-CERT-1";

const hex = (bytes: Uint8Array) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

function compare(a: Uint8Array, b: Uint8Array): number {
  for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return a[i] - b[i];
  return a.length - b.length;
}

async function sha256(data: Uint8Array): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", data as BufferSource));
}

export interface CertificateLeaf {
  deposit_id: string;
  material: string;
  grams: number;
}

/** `0x`-prefixed root of the sorted leaf digests, each parent hashing its children in sorted order. */
export async function certificateRoot(leaves: CertificateLeaf[]): Promise<string> {
  const enc = new TextEncoder();
  let level = await Promise.all(leaves.map((l) => sha256(enc.encode(`${l.deposit_id}|${l.material}|${l.grams}`))));
  level.sort(compare);
  if (level.length === 0) return `0x${"00".repeat(32)}`;
  while (level.length > 1) {
    const next: Uint8Array[] = [];
    for (let i = 0; i < level.length; i += 2) {
      if (i + 1 === level.length) next.push(level[i]);
      else {
        const [a, b] = [level[i], level[i + 1]].sort(compare);
        const joined = new Uint8Array(64);
        joined.set(a, 0);
        joined.set(b, 32);
        next.push(await sha256(joined));
      }
    }
    level = next;
  }
  return `0x${hex(level[0])}`;
}

/** The data the anchor transaction must carry: prefix, the certificate's 16-byte id, the root. */
export function anchorData(certificateId: string, root: string): string {
  const prefix = hex(new TextEncoder().encode(PREFIX));
  return `0x${prefix}${certificateId.replace(/-/g, "").toLowerCase()}${root.replace(/^0x/, "").toLowerCase()}`;
}
