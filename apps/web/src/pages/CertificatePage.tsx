import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download, ExternalLink, Leaf, Loader2, Printer, ShieldCheck, XCircle } from "lucide-react";
import { MATERIALS, certificateRoot, kg, parseAnchor, type Certificate, type CertificateDocument } from "@zyrcle/client";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { IPFS_GATEWAY, RPC_URL } from "@/lib/config";

const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const monthLabel = (period: string) => {
    const [y, m] = period.split("-").map(Number);
    return `${MONTHS[m - 1]} de ${y}`;
};
const kgOf = (grams: number) => kg(grams / 1000, 2);

type Check = { state: "idle" | "checking" | "ok" | "bad"; detail?: string };
const short = (h: string) => `${h.slice(0, 10)}…`;

/** Recompute the root from the leaves and compare it with the anchor transaction (ADR 0027). When
 * the anchor names an IPFS copy, read that copy by the CID written on chain (not the one our server
 * reports) and check that its own leaves give the anchored root too. */
async function verify(c: Certificate): Promise<Check> {
    const root = await certificateRoot(c.leaves ?? []);
    if (root !== c.merkle_root) return { state: "bad", detail: "Las hojas publicadas no dan la raíz del certificado." };
    if (!c.anchor_tx) return { state: "bad", detail: "El certificado aún no está anclado en la cadena." };
    const res = await fetch(RPC_URL, {
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
        const r = await fetch(`${IPFS_GATEWAY.replace(/\/?$/, "/")}${anchor.cid}`);
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

function downloadCsv(c: Certificate) {
    const rows = [["deposito", "material", "gramos"], ...(c.leaves ?? []).map((l) => [l.deposit_id, l.material, String(l.grams)])];
    const url = URL.createObjectURL(new Blob([rows.map((r) => r.join(",")).join("\n")], { type: "text/csv;charset=utf-8" }));
    Object.assign(document.createElement("a"), { href: url, download: `zyrcle-certificado-${c.period}.csv` }).click();
    URL.revokeObjectURL(url);
}

/** A host's impact certificate, verifiable by anyone (docs/adr/0027). */
const CertificatePage = () => {
    const { certificateId } = useParams();
    const { data: c, isError } = useQuery({ queryKey: ["certificate", certificateId], queryFn: () => api.certificate(certificateId!) });
    const [check, setCheck] = useState<Check>({ state: "idle" });

    const run = async () => {
        if (!c) return;
        setCheck({ state: "checking" });
        try {
            setCheck(await verify(c));
        } catch (e) {
            setCheck({ state: "bad", detail: e instanceof Error ? e.message : String(e) });
        }
    };

    return (
        <div className="min-h-screen flex flex-col">
            <div className="print:hidden"><Navbar /></div>
            <div className="print:hidden"><PageHeader title="Certificado de impacto" place={c?.host.name} /></div>
            <main className="flex-grow bg-gray-50 print:bg-white">
                <div className="container mx-auto px-4 py-8 max-w-4xl">
                    {!c ? (
                        isError ? <p className="text-center text-eco-forest/70 py-20">No encontramos ese certificado.</p> : <Loader2 className="h-10 w-10 mx-auto my-20 animate-spin text-eco-emerald" aria-label="Cargando" />
                    ) : (
                        <div className="space-y-6">
                            <Card className="shadow-sm border-0 rounded-xl bg-white">
                                <CardHeader className="bg-eco-forest/5 rounded-t-xl text-center">
                                    <Leaf className="h-10 w-10 mx-auto text-eco-emerald" />
                                    <CardTitle className="text-2xl text-eco-forest">Certificado de impacto</CardTitle>
                                    <CardDescription className="text-eco-forest/80 text-base">
                                        {c.site ? `${c.site.name} · ` : ""}{c.host.name} · {monthLabel(c.period)}
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="p-6 space-y-6">
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-center">
                                        <div className="rounded-xl bg-eco-forest/5 p-4">
                                            <p className="text-xs text-eco-forest/70">Material recuperado y vendido a un reciclador</p>
                                            <p className="text-2xl font-bold text-eco-forest mt-1">{kgOf(c.grams)}</p>
                                        </div>
                                        <div className="rounded-xl bg-gradient-to-br from-eco-emerald/80 to-eco-forest/80 text-white p-4">
                                            <p className="text-xs text-white/90">CO₂e evitado frente al relleno sanitario</p>
                                            <p className="text-2xl font-bold mt-1">{kgOf(c.co2e_g)}</p>
                                        </div>
                                        <div className="rounded-xl bg-eco-forest/5 p-4">
                                            <p className="text-xs text-eco-forest/70">Depósitos verificados</p>
                                            <p className="text-2xl font-bold text-eco-forest mt-1">{c.deposits}</p>
                                            <p className="text-xs text-eco-forest/60">de {c.participants} {c.participants === 1 ? "persona" : "personas"}</p>
                                        </div>
                                    </div>
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead>Material</TableHead>
                                                <TableHead className="text-right">Recuperado</TableHead>
                                                <TableHead className="text-right">CO₂e evitado</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {Object.entries(c.by_material).map(([m, v]) => (
                                                <TableRow key={m}>
                                                    <TableCell>{MATERIALS[m] ?? m}</TableCell>
                                                    <TableCell className="text-right">{kgOf(v.grams)}</TableCell>
                                                    <TableCell className="text-right">{kgOf(v.co2e_g)}</TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                    <p className="text-xs text-eco-forest/70">
                                        Cuenta solo el material que llegó a un comprador. Las emisiones evitadas usan los factores de reciclaje frente a relleno de
                                        EPA WARM versión 16 (diciembre de 2023). Es una cifra indicativa: no es un crédito de carbono. Emitido por {c.issued_by} el{" "}
                                        {new Date(c.created_at).toLocaleDateString("es-CO", { dateStyle: "long" })}.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card className="shadow-sm border-0 rounded-xl bg-white print:hidden">
                                <CardHeader>
                                    <CardTitle className="text-lg text-eco-forest flex items-center gap-2">
                                        <ShieldCheck className="h-5 w-5 text-eco-emerald" /> Verifícalo tú
                                    </CardTitle>
                                    <CardDescription>
                                        Tu navegador recalcula la huella de los {c.leaves?.length ?? 0} depósitos y la compara con la que quedó escrita en ZyrcleChain
                                        {c.ipfs_cid ? " y con la copia permanente del certificado en IPFS" : ""}. No depende de nuestro servidor.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    <div className="flex flex-wrap gap-2">
                                        <Button onClick={run} disabled={check.state === "checking"}>
                                            {check.state === "checking" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <ShieldCheck className="h-4 w-4 mr-1" />}
                                            Verificar
                                        </Button>
                                        <Button variant="outline" onClick={() => window.print()}>
                                            <Printer className="h-4 w-4 mr-1" /> Imprimir
                                        </Button>
                                        <Button variant="outline" onClick={() => downloadCsv(c)}>
                                            <Download className="h-4 w-4 mr-1" /> Depósitos (CSV)
                                        </Button>
                                    </div>
                                    {check.state === "ok" && (
                                        <p className="text-sm text-eco-forest flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-eco-emerald" /> Coincide. {check.detail}</p>
                                    )}
                                    {check.state === "bad" && (
                                        <p className="text-sm text-red-700 flex items-center gap-2"><XCircle className="h-4 w-4" /> No coincide. {check.detail}</p>
                                    )}
                                    <p className="text-xs text-eco-forest/60 font-mono break-all">Raíz: {c.merkle_root}</p>
                                    {c.ipfs_url && (
                                        <p className="text-xs text-eco-forest/70 break-all">
                                            <a href={c.ipfs_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline text-eco-forest">
                                                Copia permanente en IPFS <ExternalLink className="h-3 w-3" />
                                            </a>
                                            <span className="font-mono text-eco-forest/60"> · {c.ipfs_cid}</span>
                                        </p>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    )}
                </div>
            </main>
            <div className="print:hidden"><Footer /></div>
        </div>
    );
};

export default CertificatePage;
