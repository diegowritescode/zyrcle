import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MATERIALS, pesos } from "@zyrcle/client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Center, SiteRow } from "@/console/api";
import { useConsole } from "@/console/context";
import { failed } from "@/console/format";
import { Empty, Loading, Section } from "./shared";

/** Collection centers, what each pays per material, and the sites that sell to each (docs/adr/0037).
 * A site's advances use its center's price; the general table below is the fallback. */
export function Centers() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const centers = useQuery({ queryKey: ["op", "centers"], queryFn: api.centers });
    const sites = useQuery({ queryKey: ["op", "sites"], queryFn: api.sites });
    const [name, setName] = useState("");
    const [taxId, setTaxId] = useState("");

    const create = async () => {
        try {
            await api.createCenter({ name: name.trim(), tax_id: taxId.trim() || null });
            setName("");
            setTaxId("");
            await queryClient.invalidateQueries({ queryKey: ["op", "centers"] });
        } catch (e) {
            failed(e);
        }
    };

    return (
        <Section title="Centros de acopio" description="Cada sede le vende a un centro. El anticipo de esa sede usa el precio de su centro; si el centro no tiene precio para un material, usa la tabla general">
            <form
                className="flex flex-wrap items-end gap-2 mb-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    if (name.trim()) create();
                }}
            >
                <div className="space-y-1">
                    <Label htmlFor="center-name">Nombre del centro</Label>
                    <Input id="center-name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="center-nit">NIT</Label>
                    <Input id="center-nit" value={taxId} onChange={(e) => setTaxId(e.target.value)} className="w-40" />
                </div>
                <Button type="submit" disabled={!name.trim()}>Agregar centro</Button>
            </form>
            {!centers.data ? <Loading /> : centers.data.length === 0 ? <Empty text="Aún no hay centros de acopio." /> : (
                <div className="space-y-6">
                    {centers.data.map((c) => <CenterCard key={c.id} center={c} sites={sites.data ?? []} />)}
                </div>
            )}
        </Section>
    );
}

function CenterCard({ center, sites }: { center: Center; sites: SiteRow[] }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const suggestions = useQuery({ queryKey: ["op", "centers", center.id, "suggested"], queryFn: () => api.centerSuggestions(center.id) });
    const free = sites.filter((s) => s.center_id !== center.id);

    const assign = async (siteId: string, centerId: string | null) => {
        try {
            await api.setSiteCenter(siteId, centerId);
            await queryClient.invalidateQueries({ queryKey: ["op", "centers"] });
            await queryClient.invalidateQueries({ queryKey: ["op", "sites"] });
        } catch (e) {
            failed(e);
        }
    };

    return (
        <div className="rounded-xl border border-eco-forest/10 p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
                <p className="font-semibold text-eco-forest">{center.name}</p>
                {center.tax_id && <p className="text-xs text-eco-forest/60">NIT {center.tax_id}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-3">
                <span className="text-sm text-eco-forest/70">Le venden:</span>
                {center.sites.length === 0 && <span className="text-sm text-eco-forest/50">ninguna sede todavía</span>}
                {center.sites.map((s) => (
                    <Button key={s.id} size="sm" variant="secondary" onClick={() => assign(s.id, null)} aria-label={`Quitar ${s.name}`}>
                        {s.name} ✕
                    </Button>
                ))}
                {free.length > 0 && (
                    <Select value="" onValueChange={(siteId) => assign(siteId, center.id)}>
                        <SelectTrigger className="w-56" aria-label={`Agregar una sede a ${center.name}`}><SelectValue placeholder="Agregar una sede" /></SelectTrigger>
                        <SelectContent>
                            {free.map((s) => <SelectItem key={s.id} value={s.id}>{s.name} · {s.host_name}</SelectItem>)}
                        </SelectContent>
                    </Select>
                )}
            </div>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Material</TableHead>
                        <TableHead>Precio por kilo</TableHead>
                        <TableHead>Según sus ventas (90 días)</TableHead>
                        <TableHead />
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {Object.keys(MATERIALS).map((m) => (
                        <CenterPriceRow key={m} center={center} material={m} suggested={suggestions.data?.[m]} />
                    ))}
                </TableBody>
            </Table>
        </div>
    );
}

function CenterPriceRow({ center, material, suggested }: { center: Center; material: string; suggested?: { cop_per_kg: number; lines: number } }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const current = center.prices[material];
    const [value, setValue] = useState(current ? String(current.cop_per_kg) : "");
    const save = async (cop: number, source: "manual" | "sales") => {
        try {
            await api.setCenterPrice(center.id, material, cop, source);
            setValue(String(cop));
            toast.success(`${center.name}, ${MATERIALS[material] ?? material}: ${pesos(cop)} por kilo`);
            await queryClient.invalidateQueries({ queryKey: ["op", "centers"] });
        } catch (e) {
            failed(e);
        }
    };
    return (
        <TableRow>
            <TableCell className="font-medium">{MATERIALS[material] ?? material}</TableCell>
            <TableCell>
                <Input type="number" min={0} className="w-32" value={value} onChange={(e) => setValue(e.target.value)} aria-label={`Precio de ${material} en ${center.name}`} />
            </TableCell>
            <TableCell className="text-sm text-eco-forest/70">
                {suggested ? (
                    <Button size="sm" variant="ghost" onClick={() => save(suggested.cop_per_kg, "sales")}>
                        Usar {pesos(suggested.cop_per_kg)} ({suggested.lines} {suggested.lines === 1 ? "venta" : "ventas"})
                    </Button>
                ) : "—"}
            </TableCell>
            <TableCell className="text-right">
                <Button size="sm" variant="outline" disabled={value === "" || Number(value) === current?.cop_per_kg} onClick={() => save(Number(value), "manual")}>Guardar</Button>
            </TableCell>
        </TableRow>
    );
}
