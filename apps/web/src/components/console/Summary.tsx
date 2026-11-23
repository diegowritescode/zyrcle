import { useQuery } from "@tanstack/react-query";
import { dateTime, grams, pesos } from "@zyrcle/client";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { useConsole } from "@/console/context";
import { Empty, Loading, Section, Stat } from "./shared";

const blockAge = (s: number) => (s < 120 ? `${s} s` : s < 7_200 ? `${Math.round(s / 60)} min` : `${Math.round(s / 3_600)} h`);

/** What needs the operator now, and the Treasury's books. */
export function Summary() {
    const { api } = useConsole();
    const treasury = useQuery({ queryKey: ["op", "treasury"], queryFn: api.treasury, refetchInterval: 15_000 });
    const review = useQuery({ queryKey: ["op", "review"], queryFn: api.reviewQueue, refetchInterval: 15_000 });
    const incidents = useQuery({ queryKey: ["op", "incidents", "open"], queryFn: () => api.incidents("open"), refetchInterval: 15_000 });
    const sales = useQuery({ queryKey: ["op", "sales"], queryFn: api.sales, refetchInterval: 15_000 });
    const balance = useQuery({ queryKey: ["op", "balance"], queryFn: api.containersBalance, refetchInterval: 30_000 });
    const health = useQuery({ queryKey: ["op", "health"], queryFn: api.health, refetchInterval: 30_000 });
    const h = health.data;

    const toConfirm = sales.data?.filter((s) => s.status === "recorded").length;
    const waiting = sales.data?.flatMap((s) => s.lines).filter((l) => l.status === "waiting" || l.status === "failed").length;
    const t = treasury.data;

    return (
        <div className="space-y-6">
            <Section title="Pendientes" description="Lo que espera una decisión tuya">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="Depósitos en revisión" value={review.data?.length ?? "—"} />
                    <Stat label="Incidentes abiertos" value={incidents.data?.length ?? "—"} hint="Frenan la venta de sus bolsas" />
                    <Stat label="Ventas por confirmar" value={toConfirm ?? "—"} hint="Falta ver el pago en el banco" />
                    <Stat label="Bolsas sin liquidar" value={waiting ?? "—"} hint="Esperando o con error" />
                </div>
            </Section>

            <Section title="Estado del sistema" description="Colas, contenedores, cadena y gas. Los avisos también llegan por correo a los administradores, una vez al día">
                {!h ? (
                    <Loading />
                ) : (
                    <div className="space-y-4">
                        {h.ok ? (
                            <p className="text-sm text-eco-forest">Todo funciona: las colas avanzan y la cadena produce bloques.</p>
                        ) : (
                            <ul className="space-y-1">
                                {h.warnings.map((w) => (
                                    <li key={w.kind} className="text-sm rounded-lg bg-amber-50 text-amber-900 px-3 py-2">{w.text}</li>
                                ))}
                            </ul>
                        )}
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                            <Stat label="Contenedores en línea" value={`${h.devices.online} de ${h.devices.total}`} />
                            <Stat label="Broker MQTT" value={h.mqtt ? "Conectado" : "Sin conexión"} />
                            <Stat label="Último bloque" value={h.chain?.block ?? "—"} hint={h.chain?.block_age_s !== undefined ? `hace ${blockAge(h.chain.block_age_s)} · solo hay bloques cuando hay transacciones` : undefined} />
                            {Object.entries(h.chain?.keys ?? {}).map(([role, k]) => (
                                <Stat key={role} label={`Gas de la llave ${role}`} value={`${k.zyr} ZYR`} />
                            ))}
                        </div>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Cola</TableHead>
                                    <TableHead>Pendientes</TableHead>
                                    <TableHead>Con error</TableHead>
                                    <TableHead>La más vieja</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {h.outboxes.map((o) => (
                                    <TableRow key={o.name}>
                                        <TableCell className="font-medium">{o.name}</TableCell>
                                        <TableCell>{o.pending}</TableCell>
                                        <TableCell>{o.failed ? <Badge variant="destructive">{o.failed}</Badge> : 0}</TableCell>
                                        <TableCell>{o.oldest_pending_min === null ? "—" : `${o.oldest_pending_min} min`}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                )}
            </Section>

            <Section title="Tesorería" description="ZYR solo existe respaldado por pesos recibidos (1 ZYR = 1 peso)">
                {t ? (
                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                        <Stat label="Respaldo" value={pesos(t.backing_cop)} hint="Semilla + partes repartibles de ventas" />
                        <Stat label="Emitido" value={pesos(t.minted_cop)} />
                        <Stat label="Disponible" value={pesos(t.available_cop)} hint="Lo que aún puede pagarse" />
                        <Stat label="Capital semilla" value={pesos(t.seed_capital_cop)} />
                        <Stat label="Ingresos de operación" value={pesos(t.operations_revenue_cop)} hint="En pesos, no se emiten" />
                    </div>
                ) : treasury.isError ? (
                    <Empty>La cadena no está configurada o no responde.</Empty>
                ) : (
                    <Loading />
                )}
            </Section>

            <Section title="Contenedores" description="Su última recolección y si algo no cuadra">
                {balance.data ? (
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Contenedor</TableHead>
                                <TableHead>Última recolección</TableHead>
                                <TableHead>Quedó dentro</TableHead>
                                <TableHead>Incidentes</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {balance.data.map((c) => (
                                <TableRow key={c.container_id}>
                                    <TableCell className="font-medium">{c.name}</TableCell>
                                    <TableCell>{c.last_collection_at ? dateTime(c.last_collection_at) : "Nunca"}</TableCell>
                                    <TableCell>{c.left_after_g === null ? "—" : grams(Math.max(c.left_after_g, 0))}</TableCell>
                                    <TableCell>{c.open_incidents ? <Badge variant="destructive">{c.open_incidents} abierto(s)</Badge> : <Badge variant="outline">Cuadra</Badge>}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                ) : (
                    <Loading />
                )}
            </Section>
        </div>
    );
}
