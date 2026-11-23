import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, pesos, shortHex } from "@zyrcle/client";
import { Banknote, Store, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { OperatorRedemption } from "@/console/api";
import { useConsole } from "@/console/context";
import { failed } from "@/console/format";
import { Empty, Loading, Section } from "./shared";

const NONE = "none";
const STATUS: Record<string, string> = { requested: "Enviando", pending: "Por pagar", settled: "Pagado", refunded: "Devuelto", failed: "Falló" };

/** Campus merchants and their redemptions of ZYR for pesos (docs/adr/0029). */
export function Merchants() {
    return (
        <div className="space-y-6">
            <Redemptions />
            <MerchantList />
        </div>
    );
}

function Redemptions() {
    const { api } = useConsole();
    const list = useQuery({ queryKey: ["op", "redemptions"], queryFn: () => api.redemptions(), refetchInterval: 10_000 });
    return (
        <Section title="Cambios de ZYR a pesos" description="Transfiere los pesos a la cuenta del comercio y confirma con la referencia del banco; así se retiran esos ZYR">
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>No hay cambios pedidos.</Empty> : (
                <div className="space-y-3">
                    {list.data.map((r) => <RedemptionRow key={r.id} r={r} />)}
                </div>
            )}
        </Section>
    );
}

function RedemptionRow({ r }: { r: OperatorRedemption }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [bankRef, setBankRef] = useState("");
    const [busy, setBusy] = useState(false);
    const decide = async (settle: boolean) => {
        setBusy(true);
        try {
            if (settle) await api.settleRedemption(r.id, bankRef.trim());
            else await api.refundRedemption(r.id);
            toast.success(settle ? "Pagado: los ZYR quedan retirados" : "Devuelto al comercio");
            await queryClient.invalidateQueries({ queryKey: ["op"] });
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="rounded-xl border border-gray-100 p-4 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-semibold text-eco-forest">{r.merchant} · NIT {r.nit}</p>
                <div className="flex items-center gap-2">
                    <span className="font-semibold">{pesos(r.amount_cop)}</span>
                    <Badge variant={r.status === "pending" ? "destructive" : "outline"}>{STATUS[r.status] ?? r.status}</Badge>
                </div>
            </div>
            <p className="text-xs text-eco-forest/60">
                {dateTime(r.created_at)}
                {r.decided_by && ` · decidió ${r.decided_by}`}
                {r.bank_ref && ` · ${r.bank_ref}`}
            </p>
            {r.status === "pending" && (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                    <div className="space-y-1">
                        <Label htmlFor={`bank-${r.id}`}>Referencia de la transferencia</Label>
                        <Input id={`bank-${r.id}`} value={bankRef} onChange={(e) => setBankRef(e.target.value)} />
                    </div>
                    <Button disabled={busy || !bankRef.trim()} onClick={() => decide(true)}>
                        <Banknote className="h-4 w-4 mr-1" /> Ya pagué
                    </Button>
                    <Button variant="outline" disabled={busy} onClick={() => decide(false)}>
                        <Undo2 className="h-4 w-4 mr-1" /> Devolver
                    </Button>
                </div>
            )}
        </div>
    );
}

function MerchantList() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const list = useQuery({ queryKey: ["op", "merchants"], queryFn: api.merchants });
    const hosts = useQuery({ queryKey: ["op", "hosts"], queryFn: api.hosts });
    const [address, setAddress] = useState("");
    const [name, setName] = useState("");
    const [nit, setNit] = useState("");
    const [hostId, setHostId] = useState(NONE);

    const add = async () => {
        try {
            await api.nameMerchant({ address: address.trim(), name: name.trim(), nit: nit.trim(), host_id: hostId === NONE ? null : hostId });
            toast.success(`${name} ya cobra con Zyrcle: verá «Comercio» en su app`);
            setAddress("");
            setName("");
            setNit("");
            await queryClient.invalidateQueries({ queryKey: ["op", "merchants"] });
        } catch (e) {
            failed(e);
        }
    };

    return (
        <Section title="Comercios" description="Solo negocios con su KYC hecho: el NIT y el certificado de existencia se revisan antes de agregarlos">
            <form
                className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[2fr_1.5fr_1fr_1.5fr_auto] items-end mb-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    add();
                }}
            >
                <div className="space-y-1">
                    <Label htmlFor="m-address">Dirección de su cuenta</Label>
                    <Input id="m-address" placeholder="0x…" value={address} onChange={(e) => setAddress(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="m-name">Nombre del negocio</Label>
                    <Input id="m-name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="m-nit">NIT</Label>
                    <Input id="m-nit" value={nit} onChange={(e) => setNit(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label>Campus</Label>
                    <Select value={hostId} onValueChange={setHostId}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value={NONE}>Ninguno</SelectItem>
                            {(hosts.data ?? []).map((h) => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <Button type="submit" disabled={!/^0x[0-9a-fA-F]{40}$/.test(address.trim()) || !name.trim() || nit.trim().length < 3}>
                    <Store className="h-4 w-4 mr-1" /> Agregar
                </Button>
            </form>
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>Aún no hay comercios.</Empty> : (
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Negocio</TableHead>
                            <TableHead>NIT</TableHead>
                            <TableHead>Cuenta</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.data.map((m) => (
                            <TableRow key={m.resident_id} className={m.active ? "" : "opacity-60"}>
                                <TableCell className="font-medium">{m.name}</TableCell>
                                <TableCell>{m.nit}</TableCell>
                                <TableCell className="font-mono text-xs">{shortHex(m.address)}</TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
        </Section>
    );
}
