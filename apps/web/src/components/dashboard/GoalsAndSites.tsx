import { useQuery } from "@tanstack/react-query";
import { Target } from "lucide-react";
import { kg, type MonthFigures } from "@zyrcle/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";

const monthName = (period: string, style: "long" | "short" = "long") => {
    const [y, m] = period.split("-").map(Number);
    return new Date(y, m - 1, 1).toLocaleDateString("es-CO", { month: style });
};

/** The last months as small bars, the running one last; the numbers are in its label. */
function Trend({ months }: { months: MonthFigures[] }) {
    const top = Math.max(...months.map((m) => m.kg), 0.001);
    const label = months.map((m) => `${monthName(m.period, "short")}: ${kg(m.kg)}`).join(", ");
    return (
        <div className="flex items-end gap-1 h-8" role="img" aria-label={label} title={label}>
            {months.map((m, i) => (
                <div
                    key={m.period}
                    className={i === months.length - 1 ? "w-2.5 rounded-sm bg-eco-emerald/50" : "w-2.5 rounded-sm bg-eco-emerald"}
                    style={{ height: `${Math.max(4, (m.kg / top) * 100)}%` }}
                />
            ))}
        </div>
    );
}

function Goal({ kgNow, goal, pct }: { kgNow: number; goal: number | null; pct: number | null }) {
    if (goal === null || pct === null) return <span className="text-eco-forest/60">Sin meta</span>;
    return (
        <div className="min-w-32 space-y-1">
            <Progress value={Math.min(pct, 100)} className="h-2" aria-label={`${pct} % de ${kg(goal, 0)}`} />
            <span className="text-xs text-eco-forest/70">
                {pct} % de {kg(goal, 0)}
                {kgNow >= goal ? " · cumplida" : ""}
            </span>
        </div>
    );
}

/** A host's goals this month and the comparison between its sites (docs/adr/0046). */
export function GoalsAndSites({ hostId }: { hostId: string }) {
    const { data } = useQuery({ queryKey: ["host-progress", hostId], queryFn: () => api.hostProgress(hostId), refetchInterval: 60_000 });
    if (!data) return null;
    const month = monthName(data.period);
    return (
        <Card className="shadow-sm border-0 rounded-xl bg-white mt-8 max-w-7xl mx-auto">
            <CardHeader className="bg-eco-forest/5 rounded-t-xl">
                <CardTitle className="text-xl text-eco-forest flex items-center gap-2">
                    <Target className="h-5 w-5 text-eco-emerald" /> Metas de {month} y comparación entre sedes
                </CardTitle>
                <CardDescription className="text-eco-forest/70">
                    Kilos verificados en los contenedores este mes, que sigue en curso, frente a la meta de cada sede. Las barras muestran los últimos meses.
                </CardDescription>
            </CardHeader>
            <CardContent className="p-6 space-y-6">
                <div className="grid gap-4 sm:grid-cols-3">
                    <div>
                        <p className="text-xs text-eco-forest/70">{data.host.name}, este mes</p>
                        <p className="text-2xl font-bold text-eco-forest">{kg(data.kg)}</p>
                        <p className="text-xs text-eco-forest/60">
                            de {data.participants} {data.participants === 1 ? "persona" : "personas"}
                        </p>
                    </div>
                    <div className="sm:col-span-2 flex items-center">
                        <Goal kgNow={data.kg} goal={data.goal_kg} pct={data.progress_pct} />
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <Table aria-label="Comparación entre sedes">
                        <TableHeader>
                            <TableRow>
                                <TableHead>Sede</TableHead>
                                <TableHead className="text-right">Este mes</TableHead>
                                <TableHead>Meta</TableHead>
                                <TableHead className="text-right">Personas</TableHead>
                                <TableHead className="text-right">Por persona</TableHead>
                                <TableHead>Últimos meses</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {data.sites.map((s) => (
                                <TableRow key={s.id}>
                                    <TableCell className="font-medium">{s.name}</TableCell>
                                    <TableCell className="text-right">{kg(s.kg)}</TableCell>
                                    <TableCell>
                                        <Goal kgNow={s.kg} goal={s.goal_kg} pct={s.progress_pct} />
                                    </TableCell>
                                    <TableCell className="text-right">{s.participants}</TableCell>
                                    <TableCell className="text-right">{s.kg_per_participant === null ? "—" : kg(s.kg_per_participant)}</TableCell>
                                    <TableCell>
                                        <Trend months={s.months} />
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            </CardContent>
        </Card>
    );
}
