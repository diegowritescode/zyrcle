/**
 * Verifying an impact certificate in the browser (docs/adr/0027): rebuild the Merkle root from the
 * published leaves and compare it with the data of the transaction that anchored it. Since the
 * amendment of 2026-11-22 the anchor may also carry the CID of the certificate's copy on IPFS.
 * Mirrors apps/api/src/zyrcle_api/domain/impact.py.
 */
const PREFIX = "ZYRCLE-CERT-1";
const PREFIX_IPFS = "ZYRCLE-CERT-2";

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

/** The data the anchor transaction must carry: prefix, the certificate's 16-byte id, the root, and
 * the CID of its IPFS copy when it has one. */
export function anchorData(certificateId: string, root: string, cid?: string | null): string {
  const enc = new TextEncoder();
  const prefix = hex(enc.encode(cid ? PREFIX_IPFS : PREFIX));
  const body = `${certificateId.replace(/-/g, "").toLowerCase()}${root.replace(/^0x/, "").toLowerCase()}`;
  return `0x${prefix}${body}${cid ? hex(enc.encode(cid)) : ""}`;
}

export interface Anchor {
  certificateId: string;
  root: string;
  cid: string | null;
}

/** Read an anchor transaction's data back: what it says was certified, and where the copy is.
 * `null` when the data is not a Zyrcle certificate anchor. */
export function parseAnchor(data: string): Anchor | null {
  const raw = data.replace(/^0x/, "").toLowerCase();
  const tag = (p: string) => hex(new TextEncoder().encode(p));
  const v2 = raw.startsWith(tag(PREFIX_IPFS));
  if (!v2 && !raw.startsWith(tag(PREFIX))) return null;
  const rest = raw.slice(tag(PREFIX).length);
  if (rest.length < 96 || rest.length % 2 !== 0 || (!v2 && rest.length !== 96)) return null;
  const id = rest.slice(0, 32);
  const uuid = `${id.slice(0, 8)}-${id.slice(8, 12)}-${id.slice(12, 16)}-${id.slice(16, 20)}-${id.slice(20)}`;
  const cidHex = rest.slice(96);
  const cid = v2 ? String.fromCharCode(...(cidHex.match(/../g) ?? []).map((b) => parseInt(b, 16))) : null;
  if (v2 && !/^[A-Za-z0-9]{10,100}$/.test(cid ?? "")) return null;
  return { certificateId: uuid, root: `0x${rest.slice(32, 96)}`, cid };
}

/** The public copy of a certificate on IPFS (docs/adr/0027, amendment of 2026-11-22). */
export interface CertificateDocument {
  schema: string;
  id: string;
  period: string;
  grams: number;
  co2e_g: number;
  merkle: { root: string };
  leaves: CertificateLeaf[];
}
