import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MATERIALS, dateTime, grams, shortHex, type Bag } from "@zyrcle/client";
import { Printer, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ContainerQr } from "@/components/recycling/ContainerQr";
import { useConsole } from "@/console/context";
import { Empty, Loading, Section } from "./shared";
import { failed } from "@/console/format";

const BAG_STATUS: Record<Bag["status"], string> = { open: "Abierta", sealed: "Cerrada", sold: "Vendida", settled: "Liquidada" };

/** Collectors, bags and the collections that filled them (docs/adr/0012). */
export function Collection() {
    return (
        <div className="space-y-6">
            <Collectors />
            <Bags />
            <Collections />
        </div>
    );
}

function Collectors() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const list = useQuery({ queryKey: ["op", "collectors"], queryFn: api.collectors });
    const [address, setAddress] = useState("");
    const [name, setName] = useState("");
    const [busy, setBusy] = useState(false);

    const add = async () => {
        setBusy(true);
        try {
            await api.nameCollector(address.trim(), name.trim());
            toast.success(`${name} ya es recolector: verá «Recolección» en su app`);
            setAddress("");
            setName("");
            await queryClient.invalidateQueries({ queryKey: ["op", "collectors"] });
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };
    const toggle = async (address: string, name: string, active: boolean) => {
        try {
            await api.nameCollector(address, name, active);
            await queryClient.invalidateQueries({ queryKey: ["op", "collectors"] });
        } catch (e) {
            failed(e);
        }
    };

    return (
        <Section title="Recolectores" description="Personas que vacían contenedores. Pide la dirección que aparece en su app, en «Cuenta»">
            <form
                className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] items-end mb-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    add();
                }}
            >
                <div className="space-y-1">
                    <Label htmlFor="col-address">Dirección de su cuenta</Label>
                    <Input id="col-address" placeholder="0x…" value={address} onChange={(e) => setAddress(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="col-name">Nombre</Label>
                    <Input id="col-name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <Button type="submit" disabled={busy || !/^0x[0-9a-fA-F]{40}$/.test(address.trim()) || !name.trim()}>
                    <UserPlus className="h-4 w-4 mr-1" /> Nombrar
                </Button>
            </form>
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>Aún no hay recolectores.</Empty> : (
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Nombre</TableHead>
                            <TableHead>Cuenta</TableHead>
                            <TableHead />
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.data.map((c) => (
                            <TableRow key={c.resident_id}>
                                <TableCell className="font-medium">{c.name}</TableCell>
                                <TableCell className="font-mono text-xs">{shortHex(c.address)}</TableCell>
                                <TableCell className="text-right">
                                    <Button size="sm" variant="outline" onClick={() => toggle(c.address, c.name, !c.active)}>
                                        {c.active ? "Desactivar" : "Activar"}
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

function Bags() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [status, setStatus] = useState<string>("all");
    const list = useQuery({ queryKey: ["op", "bags", status], queryFn: () => api.bags(status === "all" ? undefined : status), refetchInterval: 15_000 });
    const [material, setMaterial] = useState("pet");
    const [count, setCount] = useState(10);
    const [labels, setLabels] = useState<Bag[]>([]);
    const [busy, setBusy] = useState(false);

    const create = async () => {
        setBusy(true);
        try {
            setLabels(await api.createBags(material, count));
            await queryClient.invalidateQueries({ queryKey: ["op", "bags"] });
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };

    return (
        <Section title="Bolsas" description="Cada bolsa lleva un QR impreso y guarda un solo material">
            <div className="flex flex-wrap items-end gap-2 mb-4 print:hidden">
                <div className="space-y-1">
                    <Label>Material</Label>
                    <Select value={material} onValueChange={setMaterial}>
                        <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {Object.entries(MATERIALS).map(([key, label]) => (
                                <SelectItem key={key} value={key}>{label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="space-y-1">
                    <Label htmlFor="bag-count">Cuántas</Label>
                    <Input id="bag-count" type="number" min={1} max={200} className="w-24" value={count} onChange={(e) => setCount(Number(e.target.value))} />
                </div>
                <Button disabled={busy || count < 1 || count > 200} onClick={create}>Crear etiquetas</Button>
            </div>

            {labels.length > 0 && (
                <div className="mb-6">
                    <div className="flex items-center justify-between mb-3 print:hidden">
                        <p className="text-sm text-eco-forest/70">{labels.length} etiquetas nuevas. Imprímelas y pega una en cada bolsa.</p>
                        <Button size="sm" variant="outline" onClick={() => window.print()}>
                            <Printer className="h-4 w-4 mr-1" /> Imprimir
                        </Button>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" id="bag-labels">
                        {labels.map((b) => (
                            <div key={b.id} className="rounded-lg border border-eco-forest/20 p-3 flex flex-col items-center gap-1 break-inside-avoid">
                                <ContainerQr value={b.qr} size={120} />
                                <p className="font-mono font-semibold tracking-widest text-eco-forest">{b.code}</p>
                                <p className="text-xs text-eco-forest/70">{MATERIALS[b.material] ?? b.material} · Zyrcle</p>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="flex gap-2 mb-3 print:hidden">
                {["all", "open", "sealed", "sold", "settled"].map((s) => (
                    <Button key={s} size="sm" variant={status === s ? "default" : "outline"} onClick={() => setStatus(s)}>
                        {s === "all" ? "Todas" : BAG_STATUS[s as Bag["status"]]}
                    </Button>
                ))}
            </div>
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>No hay bolsas con ese estado.</Empty> : (
                <Table className="print:hidden">
                    <TableHeader>
                        <TableRow>
                            <TableHead>Código</TableHead>
                            <TableHead>Material</TableHead>
                            <TableHead>Peso</TableHead>
                            <TableHead>Recolector</TableHead>
                            <TableHead>Estado</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.data.map((b) => (
                            <TableRow key={b.id}>
                                <TableCell className="font-mono">{b.code}</TableCell>
                                <TableCell>{MATERIALS[b.material] ?? b.material}</TableCell>
                                <TableCell>{grams(b.grams)}</TableCell>
                                <TableCell>{b.collector ?? "—"}</TableCell>
                                <TableCell><Badge variant={b.status === "settled" ? "default" : "outline"}>{BAG_STATUS[b.status]}</Badge></TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
        </Section>
    );
}

function Collections() {
    const { api } = useConsole();
    const list = useQuery({ queryKey: ["op", "collections"], queryFn: api.collections, refetchInterval: 15_000 });
    return (
        <Section title="Recolecciones" description="Cada vaciado, con lo que pesó cada bolsa según la báscula del contenedor">
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>Aún no hay recolecciones.</Empty> : (
                <div className="space-y-3">
                    {list.data.map((c) => (
                        <div key={c.id} className="rounded-xl border border-gray-100 p-4">
                            <div className="flex flex-wrap justify-between gap-2">
                                <p className="font-semibold text-eco-forest">{c.container_name} · {c.collector ?? "—"}</p>
                                <span className="text-xs text-eco-forest/60">{dateTime(c.created_at)} · {c.state}</span>
                            </div>
                            <div className="flex flex-wrap gap-2 mt-2 text-sm">
                                {c.removed_g !== null && <Badge variant="outline">Salió {grams(Math.max(c.removed_g, 0))}</Badge>}
                                {c.fills.map((f) => (
                                    <Badge key={f.id} variant="outline">
                                        {f.residue ? "Residuo" : `${MATERIALS[f.material ?? ""] ?? f.material} ${f.bag_code}`}: {f.grams === null ? "…" : grams(f.grams)}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </Section>
    );
}
