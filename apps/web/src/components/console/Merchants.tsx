import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, pesos, shortHex } from "@zyrcle/client";
import { Banknote, Pencil, Store, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MerchantRow, OperatorRedemption } from "@/console/api";
import { useConsole } from "@/console/context";
import { failed } from "@/console/format";
import { Empty, Loading, Section } from "./shared";

const NONE = "none";
const EMPTY_FORM = { address: "", name: "", nit: "", hostId: NONE, siteId: NONE, place: "", hours: "", offer: "" };
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
    const sites = useQuery({ queryKey: ["op", "sites"], queryFn: api.sites });
    const [form, setForm] = useState(EMPTY_FORM);
    const set = (field: keyof typeof EMPTY_FORM) => (value: string) => setForm((f) => ({ ...f, [field]: value }));
    const hostSites = (sites.data ?? []).filter((s) => s.host_id === form.hostId);
    const editing = list.data?.some((m) => m.address.toLowerCase() === form.address.trim().toLowerCase());

    const save = async () => {
        try {
            await api.nameMerchant({
                address: form.address.trim(),
                name: form.name.trim(),
                nit: form.nit.trim(),
                host_id: form.hostId === NONE ? null : form.hostId,
                site_id: form.siteId === NONE ? null : form.siteId,
                place: form.place,
                hours: form.hours,
                offer: form.offer,
            });
            toast.success(editing ? `${form.name}: datos guardados` : `${form.name} ya cobra con Zyrcle: verá «Comercio» en su app`);
            setForm(EMPTY_FORM);
            await queryClient.invalidateQueries({ queryKey: ["op", "merchants"] });
        } catch (e) {
            failed(e);
        }
    };
    const edit = (m: MerchantRow) =>
        setForm({
            address: m.address,
            name: m.name,
            nit: m.nit,
            hostId: m.host_id ?? NONE,
            siteId: m.site_id ?? NONE,
            place: m.place ?? "",
            hours: m.hours ?? "",
            offer: m.offer ?? "",
        });

    return (
        <Section title="Comercios" description="Solo negocios con su KYC hecho: el NIT y el certificado de existencia se revisan antes de agregarlos. Con campus, sede, ubicación y horario, los participantes los ven en «Dónde gastar»">
            <form
                className="space-y-2 mb-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    save();
                }}
            >
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[2fr_1.5fr_1fr_1.5fr_1.5fr] items-end">
                    <div className="space-y-1">
                        <Label htmlFor="m-address">Dirección de su cuenta</Label>
                        <Input id="m-address" placeholder="0x…" value={form.address} onChange={(e) => set("address")(e.target.value)} />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="m-name">Nombre del negocio</Label>
                        <Input id="m-name" value={form.name} onChange={(e) => set("name")(e.target.value)} />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="m-nit">NIT</Label>
                        <Input id="m-nit" value={form.nit} onChange={(e) => set("nit")(e.target.value)} />
                    </div>
                    <div className="space-y-1">
                        <Label>Campus</Label>
                        <Select value={form.hostId} onValueChange={(v) => setForm((f) => ({ ...f, hostId: v, siteId: NONE }))}>
                            <SelectTrigger aria-label="Campus"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value={NONE}>Ninguno</SelectItem>
                                {(hosts.data ?? []).map((h) => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1">
                        <Label>Sede del comercio</Label>
                        <Select value={form.siteId} onValueChange={set("siteId")} disabled={form.hostId === NONE}>
                            <SelectTrigger aria-label="Sede del comercio"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value={NONE}>Sin sede</SelectItem>
                                {hostSites.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_2fr_auto] items-end">
                    <div className="space-y-1">
                        <Label htmlFor="m-place">Dónde queda</Label>
                        <Input id="m-place" placeholder="Bloque 7, primer piso" maxLength={200} value={form.place} onChange={(e) => set("place")(e.target.value)} />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="m-hours">Horario</Label>
                        <Input id="m-hours" placeholder="L-V 7:00 a 18:00" maxLength={120} value={form.hours} onChange={(e) => set("hours")(e.target.value)} />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="m-offer">Qué vende</Label>
                        <Input id="m-offer" placeholder="Café, almuerzos, papelería" maxLength={300} value={form.offer} onChange={(e) => set("offer")(e.target.value)} />
                    </div>
                    <Button type="submit" disabled={!/^0x[0-9a-fA-F]{40}$/.test(form.address.trim()) || !form.name.trim() || form.nit.trim().length < 3}>
                        <Store className="h-4 w-4 mr-1" /> {editing ? "Guardar" : "Agregar"}
                    </Button>
                </div>
            </form>
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>Aún no hay comercios.</Empty> : (
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Negocio</TableHead>
                            <TableHead>NIT</TableHead>
                            <TableHead>Dónde gastar</TableHead>
                            <TableHead>Cuenta</TableHead>
                            <TableHead />
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.data.map((m) => (
                            <TableRow key={m.resident_id} className={m.active ? "" : "opacity-60"}>
                                <TableCell className="font-medium">{m.name}</TableCell>
                                <TableCell>{m.nit}</TableCell>
                                <TableCell className="text-xs text-eco-forest/70">
                                    {m.host_id ? [m.place, m.hours].filter(Boolean).join(" · ") || "Sin ubicación" : "No aparece: sin campus"}
                                </TableCell>
                                <TableCell className="font-mono text-xs">{shortHex(m.address)}</TableCell>
                                <TableCell className="text-right">
                                    <Button size="sm" variant="outline" onClick={() => edit(m)} aria-label={`Editar ${m.name}`}>
                                        <Pencil className="h-3.5 w-3.5 mr-1" /> Editar
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
        </Section>
    );
}
