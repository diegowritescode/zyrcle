import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
    ArrowUp,
    BarChart3,
    CircleDollarSign,
    ExternalLink,
    Info,
    Layers,
    Recycle,
    Users,
    Weight,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from "recharts";
import { Tooltip as UITooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusPill } from "@/components/recycling/StatusPill";
import {
    type DailySeries,
    type DashboardContainer,
    type SiteRef,
    type Totals,
    dateTime,
    kg,
    pesos,
    shortDay,
    FAMILIES,
    FAMILY_OF,
    MATERIALS,
    familyOf,
    type Family,
} from "@zyrcle/client";

const tooltipStyle = {
    backgroundColor: "#fff",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
};

const kgTick = (v: number) => v.toLocaleString("es-CO", { maximumFractionDigits: 2 });
const copTick = (v: number) => v.toLocaleString("es-CO");

function downloadCsv(name: string, rows: (string | number)[][]) {
    const csv = rows.map((r) => r.join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    a.click();
    URL.revokeObjectURL(url);
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex items-center justify-between gap-4">
            <span className="text-sm font-medium text-eco-forest/80">{label}</span>
            <span className="text-sm font-semibold text-eco-forest flex items-center text-right">{children}</span>
        </div>
    );
}

export interface DashboardData extends DailySeries {
    /** Whose numbers these are: a site, or a host across all its sites. */
    name: string;
    totals: Totals;
    /** A site's containers, with their sensors. */
    containers?: DashboardContainer[];
    /** A host's sites, each with its own totals. */
    sites?: (SiteRef & { totals: Totals })[];
}

/** The hackathon's dashboard, drawn from the API's verified deposits and payouts: a site's, with its
 * containers, or a host's, with its sites (docs/adr/0011). */
export function IoTDashboard({ data, onSite }: { data: DashboardData; onSite?: (siteId: string) => void }) {
    const [selected, setSelected] = useState<DashboardContainer | null>(null);
    const { totals, containers, sites } = data;

    const activity = useMemo(
        () =>
            data.activity.map((d) => {
                const row: Record<string, number | string> = { name: shortDay(d.day), day: d.day };
                for (const f of FAMILIES) row[f.key] = 0;
                for (const [material, value] of Object.entries(d.kg)) {
                    const family: Family = FAMILY_OF[material] ?? "plastic";
                    row[family] = Math.round(((row[family] as number) + value) * 1000) / 1000;
                }
                return row;
            }),
        [data.activity],
    );
    const payouts = useMemo(() => data.payouts.map((d) => ({ name: shortDay(d.day), cop: d.cop })), [data.payouts]);

    const kgToday = Object.values(data.activity.at(-1)?.kg ?? {}).reduce((a, b) => a + b, 0);
    const copToday = data.payouts.at(-1)?.cop ?? 0;
    const online = containers?.filter((c) => c.online).length;
    const days = data.activity.length;

    const exportCsv = () =>
        downloadCsv(`zyrcle-${data.name.toLowerCase().replace(/\s+/g, "-")}.csv`, [
            ["dia", ...FAMILIES.map((f) => `${f.key}_kg`), "pagado_cop"],
            ...activity.map((row, i) => [row.day as string, ...FAMILIES.map((f) => row[f.key] as number), data.payouts[i]?.cop ?? 0]),
        ]);

    return (
        <div className="space-y-8 p-4 max-w-7xl mx-auto">
            {/* Encabezado principal */}
            <div className="text-center">
                <h1 className="text-3xl font-bold text-eco-forest">Panel de reciclaje</h1>
                <p className="text-eco-forest/60 mt-2">
                    Lo que recicló {data.name} y lo que se pagó por ello, verificado por los contenedores
                </p>
            </div>

            {/* Tarjetas de resumen */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <Card className="shadow-sm border-0 rounded-xl hover:scale-105 transition-transform duration-200 bg-eco-forest/5">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-eco-forest/80 flex items-center">
                            <Layers className="h-4 w-4 mr-2 text-eco-emerald" />
                            Contenedores
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center justify-between">
                            <div className="text-2xl font-bold text-eco-forest">{totals.containers}</div>
                            {online !== undefined ? (
                                <div className="text-xs text-green-600 flex items-center">
                                    <span className="h-2 w-2 rounded-full bg-green-500 mr-1" />
                                    {online} en línea
                                </div>
                            ) : (
                                sites && <div className="text-xs text-eco-forest/70">en {sites.length} {sites.length === 1 ? "sede" : "sedes"}</div>
                            )}
                        </div>
                    </CardContent>
                </Card>

                <Card className="shadow-sm border-0 rounded-xl hover:scale-105 transition-transform duration-200 bg-eco-forest/5">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-eco-forest/80 flex items-center">
                            <Weight className="h-4 w-4 mr-2 text-eco-emerald" />
                            Kilos verificados
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center justify-between">
                            <div className="text-2xl font-bold text-eco-forest">{kg(totals.kg_verified)}</div>
                            <div className="text-xs text-green-600 flex items-center">
                                <ArrowUp className="h-3 w-3 mr-1" />+{kgTick(kgToday)} hoy
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="shadow-sm border-0 rounded-xl hover:scale-105 transition-transform duration-200 bg-gradient-to-br from-eco-emerald/80 to-eco-forest/80 text-white">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-white/90 flex items-center">
                            <CircleDollarSign className="h-4 w-4 mr-2" />
                            Pagado en ZYR
                            <UITooltip>
                                <TooltipTrigger asChild>
                                    <Info className="h-3 w-3 ml-2 opacity-70" />
                                </TooltipTrigger>
                                <TooltipContent>Anticipos pagados a quienes reciclan, en ZyrcleChain (1 ZYR = 1 peso)</TooltipContent>
                            </UITooltip>
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center justify-between">
                            <div className="text-2xl font-bold">{pesos(totals.paid_cop)}</div>
                            <div className="text-xs text-white/80 flex items-center">
                                <ArrowUp className="h-3 w-3 mr-1" />+{copTick(copToday)} hoy
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="shadow-sm border-0 rounded-xl hover:scale-105 transition-transform duration-200 bg-gradient-to-br from-eco-lime/80 to-eco-emerald/80 text-white">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-white/90 flex items-center">
                            <Users className="h-4 w-4 mr-2" />
                            Personas
                            <UITooltip>
                                <TooltipTrigger asChild>
                                    <Info className="h-3 w-3 ml-2 opacity-70" />
                                </TooltipTrigger>
                                <TooltipContent>Wallets distintas con al menos un depósito verificado</TooltipContent>
                            </UITooltip>
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center justify-between">
                            <div className="text-2xl font-bold">{totals.residents}</div>
                            <div className="text-xs text-white/80">{totals.deposits_verified} depósitos</div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Gráficos */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <Card className="lg:col-span-8 shadow-sm border-0 rounded-xl bg-white">
                    <CardHeader className="bg-eco-forest/5">
                        <div className="flex justify-between items-center gap-4">
                            <div>
                                <CardTitle className="text-xl text-eco-forest">Actividad de reciclaje</CardTitle>
                                <CardDescription className="text-eco-forest/70">
                                    Kilos verificados por día y material (últimos {days} días)
                                </CardDescription>
                            </div>
                            <UITooltip>
                                <TooltipTrigger asChild>
                                    <Button variant="outline" size="sm" className="text-eco-forest hover:bg-eco-forest/10" onClick={exportCsv}>
                                        <BarChart3 className="h-5 w-5 mr-2" />
                                        Exportar
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>Descargar los datos en CSV</TooltipContent>
                            </UITooltip>
                        </div>
                    </CardHeader>
                    <CardContent className="p-6">
                        <div className="h-[350px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={activity} margin={{ top: 20, right: 30, left: 10, bottom: 10 }}>
                                    <defs>
                                        {FAMILIES.map((f) => (
                                            <linearGradient key={f.key} id={`${f.key}Gradient`} x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor={f.color} stopOpacity={0.8} />
                                                <stop offset="95%" stopColor={f.color} stopOpacity={0.2} />
                                            </linearGradient>
                                        ))}
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                                    <XAxis dataKey="name" stroke="#6b7280" fontSize={12} />
                                    <YAxis stroke="#6b7280" fontSize={12} tickFormatter={kgTick} />
                                    <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => kg(v, 2)} />
                                    <Legend verticalAlign="top" height={36} />
                                    {FAMILIES.map((f) => (
                                        <Area
                                            key={f.key}
                                            type="monotone"
                                            dataKey={f.key}
                                            name={f.label}
                                            stroke={f.color}
                                            fillOpacity={1}
                                            fill={`url(#${f.key}Gradient)`}
                                        />
                                    ))}
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>

                <Card className="lg:col-span-4 shadow-sm border-0 rounded-xl bg-white">
                    <CardHeader className="bg-eco-forest/5">
                        <CardTitle className="text-xl text-eco-forest">Pagos a quienes reciclan</CardTitle>
                        <CardDescription className="text-eco-forest/70">Pesos pagados por día en ZYR</CardDescription>
                    </CardHeader>
                    <CardContent className="p-6">
                        <div className="h-[350px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={payouts} margin={{ top: 20, right: 30, left: 10, bottom: 10 }}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                                    <XAxis dataKey="name" stroke="#6b7280" fontSize={12} />
                                    <YAxis stroke="#6b7280" fontSize={12} tickFormatter={copTick} />
                                    <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => pesos(v)} />
                                    <Bar dataKey="cop" name="Pagado" fill="#34D399" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Sedes del anfitrión */}
            {sites && (
                <div>
                    <div className="mb-6">
                        <h3 className="text-xl font-semibold text-eco-forest">Sedes</h3>
                        <p className="text-eco-forest/70 text-sm">Lo que aporta cada sede, con sus propios contenedores</p>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {sites.map((site) => (
                            <Card key={site.id} className="shadow-sm border-0 rounded-xl hover:shadow-md transition-shadow duration-200 bg-white">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-lg text-eco-forest">{site.name}</CardTitle>
                                    <CardDescription className="text-eco-forest/70">
                                        {site.totals.containers} {site.totals.containers === 1 ? "contenedor" : "contenedores"}
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="py-4">
                                    <div className="grid grid-cols-3 gap-2 text-sm">
                                        <div className="flex flex-col">
                                            <span className="text-xs text-eco-forest/80 mb-1">Kilos</span>
                                            <span className="font-semibold flex items-center">
                                                <Weight className="h-4 w-4 mr-1 text-eco-forest/80 shrink-0" />
                                                {kgTick(site.totals.kg_verified)}
                                            </span>
                                        </div>
                                        <div className="flex flex-col">
                                            <span className="text-xs text-eco-forest/80 mb-1">Pagado</span>
                                            <span className="font-semibold flex items-center">
                                                <CircleDollarSign className="h-4 w-4 mr-1 text-eco-emerald shrink-0" />
                                                {copTick(site.totals.paid_cop)}
                                            </span>
                                        </div>
                                        <div className="flex flex-col">
                                            <span className="text-xs text-eco-forest/80 mb-1">Depósitos</span>
                                            <span className="font-semibold flex items-center">
                                                <Recycle className="h-4 w-4 mr-1 text-eco-lime shrink-0" />
                                                {site.totals.deposits_verified}
                                            </span>
                                        </div>
                                    </div>
                                </CardContent>
                                {onSite && (
                                    <CardFooter>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            className="w-full text-eco-forest hover:bg-eco-forest/10"
                                            onClick={() => onSite(site.id)}
                                        >
                                            <Info className="h-4 w-4 mr-2" />
                                            Ver sede
                                        </Button>
                                    </CardFooter>
                                )}
                            </Card>
                        ))}
                    </div>
                </div>
            )}

            {/* Contenedores inteligentes */}
            {containers && (
            <div>
                <div className="flex justify-between items-center mb-6">
                    <div>
                        <h3 className="text-xl font-semibold text-eco-forest">Contenedores inteligentes</h3>
                        <p className="text-eco-forest/70 text-sm">El estado de cada contenedor, según sus propios sensores</p>
                    </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {containers.map((c) => {
                        const family = familyOf(c.accepted_materials);
                        return (
                            <Card
                                key={c.id}
                                className={`shadow-sm border-0 rounded-xl hover:shadow-md transition-shadow duration-200 ${c.online ? "bg-white" : "opacity-70 bg-gray-50"}`}
                            >
                                <CardHeader className="pb-2">
                                    <div className="flex justify-between items-start gap-2">
                                        <div>
                                            <CardTitle className="flex items-center text-lg text-eco-forest">
                                                <Recycle className={`h-6 w-6 mr-2 shrink-0 ${family.icon}`} />
                                                {c.name}
                                            </CardTitle>
                                            <CardDescription className="text-eco-forest/70">
                                                {c.accepted_materials.map((m) => MATERIALS[m] ?? m).join(" · ")}
                                            </CardDescription>
                                        </div>
                                        <StatusPill online={c.online} busy={c.busy} />
                                    </div>
                                </CardHeader>
                                <CardContent className="py-4">
                                    <div className="space-y-4">
                                        <div className="space-y-2">
                                            <div className="flex justify-between text-sm">
                                                <span className="text-eco-forest/80">Nivel de llenado</span>
                                                <span className="font-semibold">{c.fill_pct === null ? "Sin medición" : `${c.fill_pct}%`}</span>
                                            </div>
                                            <UITooltip>
                                                <TooltipTrigger asChild>
                                                    <Progress value={c.fill_pct ?? 0} className={`h-3 ${family.track}`} />
                                                </TooltipTrigger>
                                                <TooltipContent>
                                                    {c.fill_pct === null ? "Aún no hay depósitos medidos" : `${c.fill_pct}% lleno, según el sensor de distancia`}
                                                </TooltipContent>
                                            </UITooltip>
                                        </div>

                                        <div className="grid grid-cols-3 gap-2 text-sm">
                                            <div className="flex flex-col">
                                                <span className="text-xs text-eco-forest/80 mb-1">Peso actual</span>
                                                <span className="font-semibold flex items-center">
                                                    <Weight className="h-4 w-4 mr-1 text-eco-forest/80 shrink-0" />
                                                    {c.weight_kg === null ? "—" : kg(c.weight_kg)}
                                                </span>
                                            </div>
                                            <div className="flex flex-col">
                                                <span className="text-xs text-eco-forest/80 mb-1">Pagado</span>
                                                <span className="font-semibold flex items-center">
                                                    <CircleDollarSign className="h-4 w-4 mr-1 text-eco-emerald shrink-0" />
                                                    {copTick(c.paid_cop)}
                                                </span>
                                            </div>
                                            <div className="flex flex-col">
                                                <span className="text-xs text-eco-forest/80 mb-1">Depósitos</span>
                                                <span className="font-semibold flex items-center">
                                                    <Recycle className="h-4 w-4 mr-1 text-eco-lime shrink-0" />
                                                    {c.deposits_verified}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </CardContent>
                                <CardFooter>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="w-full text-eco-forest hover:bg-eco-forest/10"
                                        onClick={() => setSelected(c)}
                                    >
                                        <Info className="h-4 w-4 mr-2" />
                                        Ver detalles
                                    </Button>
                                </CardFooter>
                            </Card>
                        );
                    })}
                </div>
            </div>
            )}

            {/* Modal de detalles del contenedor */}
            <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
                <DialogContent className="sm:max-w-[425px] rounded-xl shadow-lg bg-white">
                    {selected && (
                        <>
                            <DialogHeader>
                                <DialogTitle className="text-2xl text-eco-forest flex items-center">
                                    <Recycle className={`h-6 w-6 mr-2 ${familyOf(selected.accepted_materials).icon}`} />
                                    {selected.name}
                                </DialogTitle>
                                <DialogDescription className="text-eco-forest/70">
                                    Todo lo que este contenedor ha medido y pagado
                                </DialogDescription>
                            </DialogHeader>
                            <div className="space-y-5 py-4">
                                <Row label="Estado">
                                    <StatusPill online={selected.online} busy={selected.busy} />
                                </Row>
                                <Row label="Recibe">{selected.accepted_materials.map((m) => MATERIALS[m] ?? m).join(" · ")}</Row>
                                <div className="space-y-2">
                                    <div className="flex justify-between text-sm">
                                        <span className="text-eco-forest/80">Nivel de llenado</span>
                                        <span className="font-semibold">{selected.fill_pct === null ? "Sin medición" : `${selected.fill_pct}%`}</span>
                                    </div>
                                    <Progress value={selected.fill_pct ?? 0} className={`h-3 ${familyOf(selected.accepted_materials).track}`} />
                                </div>
                                <Row label="Peso actual">{selected.weight_kg === null ? "—" : kg(selected.weight_kg, 2)}</Row>
                                <Row label="Kilos verificados">{kg(selected.kg_verified, 2)}</Row>
                                <Row label="Depósitos verificados">{selected.deposits_verified}</Row>
                                <Row label="Pagado en ZYR">{pesos(selected.paid_cop)}</Row>
                                <Row label="Último depósito">{selected.last_deposit_at ? dateTime(selected.last_deposit_at) : "—"}</Row>
                                <Row label="Última señal">{selected.last_seen_at ? dateTime(selected.last_seen_at) : "—"}</Row>
                                {!selected.online && (
                                    <div className="bg-amber-50 p-3 rounded-lg text-sm text-amber-800">
                                        Este contenedor no se ha reportado en el último minuto y medio.
                                    </div>
                                )}
                            </div>
                            <DialogFooter className="gap-2">
                                <Button asChild variant="outline" className="text-eco-forest hover:bg-eco-forest/10">
                                    <Link to={`/container/${selected.id}`} target="_blank">
                                        <ExternalLink className="h-4 w-4 mr-2" />
                                        Ver su pantalla
                                    </Link>
                                </Button>
                                <Button variant="outline" onClick={() => setSelected(null)} className="text-eco-forest hover:bg-eco-forest/10">
                                    Cerrar
                                </Button>
                            </DialogFooter>
                        </>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}
