import { useEffect, useState } from "react";
import { createPublicClient, decodeFunctionResult, encodeFunctionData, http, type Hex } from "viem";
import { CheckCircle2, Copy, Download, PenLine, ShieldCheck, XCircle } from "lucide-react";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CHAIN_ID, RPC_URL } from "@/lib/config";
import { readProposal, signersOf, withSignature, type SafeProposal } from "@/lib/multisig";

const SAFE_ABI = [
    { type: "function", name: "getOwners", stateMutability: "view", inputs: [], outputs: [{ name: "", type: "address[]" }] },
    { type: "function", name: "getThreshold", stateMutability: "view", inputs: [], outputs: [{ name: "", type: "uint256" }] },
    { type: "function", name: "nonce", stateMutability: "view", inputs: [], outputs: [{ name: "", type: "uint256" }] },
] as const;

interface Eip1193 {
    request(args: { method: string; params?: unknown[] }): Promise<unknown>;
}
const wallet = () => (window as unknown as { ethereum?: Eip1193 }).ethereum;
const short = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`;

/** Put the wallet on ZyrcleChain, adding the network the first time. */
async function onZyrcleChain(eth: Eip1193) {
    const chainId = `0x${CHAIN_ID.toString(16)}`;
    if ((await eth.request({ method: "eth_chainId" })) === chainId) return;
    try {
        await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId }] });
    } catch (e) {
        if ((e as { code?: number }).code !== 4902) throw e;
        await eth.request({
            method: "wallet_addEthereumChain",
            params: [{ chainId, chainName: "ZyrcleChain", nativeCurrency: { name: "ZYR", symbol: "ZYR", decimals: 18 }, rpcUrls: [RPC_URL] }],
        });
    }
}

/** Sign a Safe proposal with a wallet: MetaMask on the computer, or the phone's wallet browser
 * (docs/adr/0040). Nothing leaves this page except to the wallet and the public RPC; the signed
 * proposal is downloaded or copied and passed to the next signer. */
const Multisig = () => {
    const [text, setText] = useState("");
    const [proposal, setProposal] = useState<SafeProposal | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [safe, setSafe] = useState<{ owners: string[]; threshold: number; nonce: number } | null>(null);
    const [signers, setSigners] = useState<{ claimed: string; actual: string | null }[]>([]);
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);

    const load = (raw: string) => {
        setText(raw);
        setError(null);
        setCopied(false);
        try {
            setProposal(readProposal(raw));
        } catch (e) {
            setProposal(null);
            if (raw.trim()) setError(e instanceof Error ? e.message : String(e));
        }
    };

    useEffect(() => {
        if (!proposal) return;
        let stop = false;
        const client = createPublicClient({ transport: http(RPC_URL) });
        const to = proposal.safe as Hex;
        const read = async (functionName: "getOwners" | "getThreshold" | "nonce") => {
            const { data } = await client.call({ to, data: encodeFunctionData({ abi: SAFE_ABI, functionName }) });
            return decodeFunctionResult({ abi: SAFE_ABI, functionName, data: data ?? "0x" });
        };
        Promise.all([read("getOwners") as Promise<readonly string[]>, read("getThreshold") as Promise<bigint>, read("nonce") as Promise<bigint>])
            .then(([owners, threshold, nonce]) => !stop && setSafe({ owners: [...owners], threshold: Number(threshold), nonce: Number(nonce) }))
            .catch(() => !stop && setError("No pudimos leer el Safe en ZyrcleChain."));
        signersOf(proposal).then((s) => !stop && setSigners(s));
        return () => {
            stop = true;
        };
    }, [proposal]);

    const isOwner = (a: string | null) => !!a && !!safe?.owners.some((o) => o.toLowerCase() === a.toLowerCase());
    const valid = signers.filter((s) => s.actual && s.actual.toLowerCase() === s.claimed.toLowerCase() && isOwner(s.actual));

    const sign = async () => {
        const eth = wallet();
        if (!eth || !proposal) {
            setError("No encontramos una billetera. Abre esta página en MetaMask (en el computador o en su navegador del celular).");
            return;
        }
        setBusy(true);
        setError(null);
        try {
            const [account] = (await eth.request({ method: "eth_requestAccounts" })) as string[];
            if (!isOwner(account)) throw new Error(`La cuenta ${short(account)} no es dueña de este Safe.`);
            await onZyrcleChain(eth);
            const signature = (await eth.request({ method: "eth_signTypedData_v4", params: [account, JSON.stringify(proposal.typed_data)] })) as string;
            const { proposal: next, signer } = await withSignature(proposal, signature);
            if (signer.toLowerCase() !== account.toLowerCase()) throw new Error("La firma no corresponde a tu cuenta.");
            const raw = JSON.stringify(next, null, 2);
            setText(raw);
            setProposal(next);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    };
    const download = () => {
        const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
        Object.assign(document.createElement("a"), { href: url, download: `propuesta-safe-${proposal?.nonce ?? "x"}.json` }).click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="min-h-screen flex flex-col">
            <Navbar />
            <PageHeader title="Firmar en el Safe" />
            <main className="flex-grow bg-gray-50">
                <div className="container mx-auto px-4 py-8 max-w-3xl space-y-6">
                    <Card className="border-0 shadow-sm">
                        <CardHeader>
                            <CardTitle className="text-lg text-eco-forest flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-eco-emerald" /> Propuesta</CardTitle>
                            <CardDescription>Carga el archivo de la propuesta o pega su contenido. Cada cambio de los poderes de ZyrcleChain necesita dos de tres firmas.</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <div className="space-y-1">
                                <Label htmlFor="proposal-file">Archivo de la propuesta</Label>
                                <Input id="proposal-file" type="file" accept=".json,application/json" onChange={async (e) => e.target.files?.[0] && load(await e.target.files[0].text())} />
                            </div>
                            <div className="space-y-1">
                                <Label htmlFor="proposal-text">o pega la propuesta</Label>
                                <Textarea id="proposal-text" rows={5} value={text} onChange={(e) => load(e.target.value)} className="font-mono text-xs" />
                            </div>
                            {error && <p className="text-sm text-red-700 flex items-center gap-2"><XCircle className="h-4 w-4 shrink-0" /> {error}</p>}
                        </CardContent>
                    </Card>

                    {proposal && (
                        <Card className="border-0 shadow-sm">
                            <CardHeader>
                                <CardTitle className="text-lg text-eco-forest">{proposal.description}</CardTitle>
                                <CardDescription className="break-all font-mono text-xs">Huella {proposal.safe_tx_hash}</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3 text-sm">
                                <p>Safe <span className="font-mono">{short(proposal.safe)}</span> · destino <span className="font-mono">{short(proposal.to)}</span> · turno {proposal.nonce}{safe && safe.nonce !== proposal.nonce ? ` (el Safe va en el ${safe.nonce}: esta propuesta ya no sirve)` : ""}</p>
                                <p aria-label="Firmas">
                                    {valid.length} de {safe?.threshold ?? "…"} firmas
                                    {valid.map((s) => <span key={s.claimed} className="ml-2 inline-flex items-center gap-1 text-eco-emerald"><CheckCircle2 className="h-4 w-4" />{short(s.claimed)}</span>)}
                                </p>
                                <div className="flex flex-wrap gap-2">
                                    <Button onClick={sign} disabled={busy}><PenLine className="h-4 w-4 mr-1" /> Firmar con mi billetera</Button>
                                    <Button variant="outline" onClick={download}><Download className="h-4 w-4 mr-1" /> Descargar propuesta</Button>
                                    <Button variant="outline" onClick={async () => { await navigator.clipboard.writeText(text); setCopied(true); }}><Copy className="h-4 w-4 mr-1" /> {copied ? "Copiada" : "Copiar"}</Button>
                                </div>
                                {safe && valid.length >= safe.threshold && <p className="text-eco-forest">Lista para ejecutar: <span className="font-mono">zyrcle-api safe exec --proposal …</span></p>}
                            </CardContent>
                        </Card>
                    )}
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default Multisig;
