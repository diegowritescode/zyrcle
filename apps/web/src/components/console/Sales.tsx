import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MATERIALS, dateTime, grams, pesos, shortHex } from "@zyrcle/client";
import { Banknote, ChevronDown, ChevronUp, Receipt } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Sale, SaleLine, TicketScan } from "@/console/api";
import { TicketScanCard } from "./TicketScan";
import { useConsole } from "@/console/context";
import { Empty, Loading, Section } from "./shared";
import { failed } from "@/console/format";

const LINE_STATUS: Record<SaleLine["status"], string> = {
    pending: "Por liquidar",
    waiting: "Esperando",
    settling: "Liquidando",
    settled: "Liquidada",
    failed: "Error",
};
const PARTY: Record<string, string> = { deposit: "Depósito", collector: "Recolector", host: "Anfitrión" };

/** Sales from the buyer's ticket, the bank match, and the settlement of each bag (docs/adr/0013). */
export function Sales() {
    const [prefill, setPrefill] = useState<TicketScan | null>(null);
    return (
        <div className="space-y-6">
            <TicketScanCard onUse={setPrefill} />
            <NewSale prefill={prefill} />
            <SaleList />
        </div>
    );
}

interface Draft {
    buyer_g: string;
    amount_cop: string;
}

function NewSale({ prefill }: { prefill: TicketScan | null }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const sealed = useQuery({ queryKey: ["op", "bags", "sealed"], queryFn: () => api.bags("sealed"), refetchInterval: 15_000 });
    const [buyer, setBuyer] = useState("");
    const centers = useQuery({ queryKey: ["op", "centers"], queryFn: api.centers });
    const [centerId, setCenterId] = useState<string | null>(null);
    const [scanId, setScanId] = useState<string | null>(null);
    const [ticket, setTicket] = useState("");
    // Today in the operator's own time zone (toISOString would give tomorrow's date at night in Colombia).
    const [soldOn, setSoldOn] = useState(() => new Date().toLocaleDateString("en-CA"));
    const [lines, setLines] = useState<Record<string, Draft>>({});
    const [busy, setBusy] = useState(false);

    // A ticket read from a photo fills the form; the operator still reviews every field.
    useEffect(() => {
        const r = prefill?.reading;
        if (!prefill || !r) return;
        setScanId(prefill.id);
        setBuyer(r.center_name ?? "");
        setCenterId(prefill.center_id);
        setTicket(r.ticket_ref ?? "");
        if (r.date && /^\d{4}-\d{2}-\d{2}$/.test(r.date)) setSoldOn(r.date);
        const next: Record<string, Draft> = {};
        r.lines.forEach((l, i) => {
            const bag = prefill.proposed_bags[i];
            if (bag) next[bag] = { buyer_g: l.kg === null ? "" : String(Math.round(l.kg * 1000)), amount_cop: l.amount_cop === null ? "" : String(Math.round(l.amount_cop)) };
        });
        setLines(next);
    }, [prefill]);

    const picked = Object.entries(lines);
    const valid =
        buyer.trim() && ticket.trim() && picked.length > 0 && picked.every(([, d]) => Number(d.buyer_g) > 0 && Number(d.amount_cop) > 0);
    const total = picked.reduce((sum, [, d]) => sum + (Number(d.amount_cop) || 0), 0);

    const toggle = (code: string, grams: number, on: boolean) =>
        setLines((prev) => {
            const next = { ...prev };
            if (on) next[code] = { buyer_g: String(grams), amount_cop: "" };
            else delete next[code];
            return next;
        });
    const edit = (code: string, field: keyof Draft, value: string) => setLines((prev) => ({ ...prev, [code]: { ...prev[code], [field]: value } }));

    const record = async () => {
        setBusy(true);
        try {
            await api.recordSale({
                buyer: buyer.trim(),
                center_id: centerId,
                ticket_scan_id: scanId,
                ticket_ref: ticket.trim(),
                sold_on: soldOn,
                lines: picked.map(([bag, d]) => ({ bag, buyer_g: Number(d.buyer_g), amount_cop: Number(d.amount_cop) })),
            });
            toast.success("Venta registrada. Confírmala cuando veas el pago en el banco.");
            setLines({});
            setTicket("");
            setScanId(null);
            await queryClient.invalidateQueries({ queryKey: ["op"] });
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };

    return (
        <Section title="Registrar una venta" description="Copia el tiquete del centro de acopio: el peso de su báscula y lo que pagó por cada bolsa">
            <div className="grid gap-3 sm:grid-cols-3 mb-4">
                <div className="space-y-1">
                    <Label htmlFor="sale-buyer">Comprador</Label>
                    <Input id="sale-buyer" placeholder="Centro de acopio…" value={buyer} onChange={(e) => { setBuyer(e.target.value); setCenterId(null); }} />
                    {(centers.data ?? []).length > 0 && (
                        <Select
                            value={centerId ?? ""}
                            onValueChange={(id) => {
                                setCenterId(id);
                                setBuyer(centers.data?.find((c) => c.id === id)?.name ?? "");
                            }}
                        >
                            <SelectTrigger aria-label="Centro de acopio registrado"><SelectValue placeholder="o elige un centro registrado" /></SelectTrigger>
                            <SelectContent>
                                {(centers.data ?? []).filter((c) => c.active).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    )}
                </div>
                <div className="space-y-1">
                    <Label htmlFor="sale-ticket">Número del tiquete</Label>
                    <Input id="sale-ticket" value={ticket} onChange={(e) => setTicket(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="sale-date">Fecha</Label>
                    <Input id="sale-date" type="date" value={soldOn} onChange={(e) => setSoldOn(e.target.value)} />
                </div>
            </div>
            {!sealed.data ? <Loading /> : sealed.data.length === 0 ? <Empty>No hay bolsas cerradas para vender.</Empty> : (
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead className="w-10" />
                            <TableHead>Bolsa</TableHead>
                            <TableHead>Peso en Zyrcle</TableHead>
                            <TableHead>Peso del comprador (g)</TableHead>
                            <TableHead>Pagó (COP)</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {sealed.data.map((b) => {
                            const d = lines[b.code];
                            return (
                                <TableRow key={b.id}>
                                    <TableCell>
                                        <Checkbox checked={!!d} onCheckedChange={(v) => toggle(b.code, b.grams, v === true)} aria-label={`Vender la bolsa ${b.code}`} />
                                    </TableCell>
                                    <TableCell>
                                        <span className="font-mono">{b.code}</span> · {MATERIALS[b.material] ?? b.material}
                                    </TableCell>
                                    <TableCell>{grams(b.grams)}</TableCell>
                                    <TableCell>
                                        <Input type="number" min={1} disabled={!d} value={d?.buyer_g ?? ""} onChange={(e) => edit(b.code, "buyer_g", e.target.value)} aria-label="Peso del comprador" className="w-32" />
                                    </TableCell>
                                    <TableCell>
                                        <Input type="number" min={1} disabled={!d} value={d?.amount_cop ?? ""} onChange={(e) => edit(b.code, "amount_cop", e.target.value)} aria-label="Pago por la bolsa" className="w-32" />
                                    </TableCell>
                                </TableRow>
                            );
                        })}
                    </TableBody>
                </Table>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3 mt-4">
                <p className="text-sm text-eco-forest/70">Total del tiquete: <strong>{pesos(total)}</strong></p>
                <Button disabled={busy || !valid} onClick={record}>
                    <Receipt className="h-4 w-4 mr-1" /> Registrar venta
                </Button>
            </div>
        </Section>
    );
}

function SaleList() {
    const { api } = useConsole();
    const list = useQuery({ queryKey: ["op", "sales"], queryFn: api.sales, refetchInterval: 5_000 });
    return (
        <Section title="Ventas" description="Nada pasa a la cadena hasta que confirmes que el pago llegó al banco">
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>Aún no hay ventas.</Empty> : (
                <div className="space-y-3">
                    {list.data.map((s) => (
                        <SaleCard key={s.id} sale={s} />
                    ))}
                </div>
            )}
        </Section>
    );
}

function SaleCard({ sale: s }: { sale: Sale }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [bankRef, setBankRef] = useState("");
    const [received, setReceived] = useState("");
    const [open, setOpen] = useState(false);
    const [busy, setBusy] = useState(false);
    const report = useQuery({ queryKey: ["op", "sale", s.id], queryFn: () => api.sale(s.id), enabled: open, refetchInterval: open ? 5_000 : false });

    const confirm = async () => {
        setBusy(true);
        try {
            await api.confirmSale(s.id, bankRef.trim(), Number(received));
            toast.success("Pago confirmado: la venta se liquida en la cadena, bolsa por bolsa");
            await queryClient.invalidateQueries({ queryKey: ["op"] });
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="rounded-xl border border-gray-100 p-4 space-y-3">
            <div className="flex flex-wrap justify-between gap-2">
                <div>
                    <p className="font-semibold text-eco-forest">{s.buyer} · tiquete {s.ticket_ref}</p>
                    <p className="text-xs text-eco-forest/60">
                        {s.sold_on} · registrada por {s.recorded_by}
                        {s.confirmed_by && ` · pago confirmado por ${s.confirmed_by} (${s.bank_ref})`}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <span className="font-semibold">{pesos(s.total_cop)}</span>
                    <Badge variant={s.status === "confirmed" ? "default" : "outline"}>{s.status === "confirmed" ? "Pagada" : "Por confirmar"}</Badge>
                </div>
            </div>
            <div className="flex flex-wrap gap-2">
                {s.lines.map((l) => (
                    <Badge key={l.id} variant="outline" title={l.reason ?? undefined}>
                        {l.bag_code} · {grams(l.buyer_g)} · {pesos(l.amount_cop)} · {LINE_STATUS[l.status]}
                    </Badge>
                ))}
            </div>
            {s.lines.some((l) => l.reason) && (
                <ul className="text-xs text-eco-forest/70 list-disc pl-5">
                    {s.lines.filter((l) => l.reason).map((l) => (
                        <li key={l.id}>{l.bag_code}: {l.reason}</li>
                    ))}
                </ul>
            )}
            {s.status === "recorded" && (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                    <div className="space-y-1">
                        <Label htmlFor={`bank-${s.id}`}>Referencia del banco</Label>
                        <Input id={`bank-${s.id}`} value={bankRef} onChange={(e) => setBankRef(e.target.value)} />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor={`recv-${s.id}`}>Monto recibido (COP)</Label>
                        <Input id={`recv-${s.id}`} type="number" value={received} onChange={(e) => setReceived(e.target.value)} />
                    </div>
                    <Button disabled={busy || !bankRef.trim() || !(Number(received) > 0)} onClick={confirm}>
                        <Banknote className="h-4 w-4 mr-1" /> Confirmar pago
                    </Button>
                </div>
            )}
            {s.status === "confirmed" && (
                <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)}>
                    {open ? <ChevronUp className="h-4 w-4 mr-1" /> : <ChevronDown className="h-4 w-4 mr-1" />}
                    Reparto
                </Button>
            )}
            {open && report.data && <Report sale={report.data} />}
        </div>
    );
}

function Report({ sale }: { sale: Sale }) {
    return (
        <div className="space-y-4">
            {sale.lines.map((l) => (
                <div key={l.id} className="space-y-2">
                    <p className="text-sm font-medium text-eco-forest">
                        Bolsa {l.bag_code} · {LINE_STATUS[l.status]}
                        {l.settled_at && ` el ${dateTime(l.settled_at)}`}
                    </p>
                    {l.settlements && l.settlements.length > 0 && (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Parte</TableHead>
                                    <TableHead>Cuenta</TableHead>
                                    <TableHead>Gramos</TableHead>
                                    <TableHead>Le toca</TableHead>
                                    <TableHead>Pagado</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {l.settlements.map((r) => (
                                    <TableRow key={`${r.party}-${r.ref}`}>
                                        <TableCell>{PARTY[r.party]}</TableCell>
                                        <TableCell className="font-mono text-xs">{r.address ? shortHex(r.address) : "sin dirección"}</TableCell>
                                        <TableCell>{grams(r.grams)}</TableCell>
                                        <TableCell>{pesos(r.share_cop)}</TableCell>
                                        <TableCell>{r.paid_cop === null ? "—" : pesos(r.paid_cop)}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                    {l.report_hash && <p className="text-xs text-eco-forest/60 font-mono">Huella del reporte: {shortHex(l.report_hash)}</p>}
                </div>
            ))}
        </div>
    );
}
