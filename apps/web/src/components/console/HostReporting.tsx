import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Mail, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { HostReporting as Reporting } from "@/console/api";
import { useConsole } from "@/console/context";
import { failed } from "@/console/format";
import { saveFile } from "@/lib/saveFile";
import { Empty, Loading, Section } from "./shared";

const STATUS: Record<Reporting["reports"][number]["status"], string> = {
    waiting: "Esperando el anclaje",
    sent: "Enviado",
    empty: "Sin material vendido",
    failed: "No se envió",
};
const goal = (text: string) => (text.trim() === "" ? null : Number(text));
const validGoal = (text: string) => text.trim() === "" || (Number.isInteger(Number(text)) && Number(text) >= 1);

/** A host's monthly report, its goals and the GreenMetric workbook (docs/adr/0046). */
export function HostReporting() {
    const { api } = useConsole();
    const hosts = useQuery({ queryKey: ["op", "hosts"], queryFn: api.hosts });
    const [hostId, setHostId] = useState("");
    const reporting = useQuery({ queryKey: ["op", "reporting", hostId], queryFn: () => api.reporting(hostId), enabled: hostId !== "" });
    const [year, setYear] = useState(() => new Date().getFullYear());
    const [busy, setBusy] = useState(false);

    const download = async () => {
        setBusy(true);
        try {
            saveFile(await api.greenmetric(hostId, year));
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };

    return (
        <Section
            title="Informe mensual, metas y rankings"
            description="El certificado del mes anterior se emite solo en los primeros días de cada mes y llega en PDF a los correos de la institución. Las metas se ven en su panel público."
        >
            <div className="flex flex-wrap items-end gap-2 mb-4">
                <div className="space-y-1">
                    <Label>Anfitrión</Label>
                    <Select value={hostId} onValueChange={setHostId}>
                        <SelectTrigger className="w-56" aria-label="Anfitrión del informe">
                            <SelectValue placeholder="Elige uno" />
                        </SelectTrigger>
                        <SelectContent>
                            {(hosts.data ?? []).map((h) => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
            </div>
            {hostId === "" ? (
                <Empty>Elige un anfitrión.</Empty>
            ) : !reporting.data ? (
                <Loading />
            ) : (
                <div className="space-y-6">
                    <ReportingForm key={hostId} data={reporting.data} />
                    <div className="flex flex-wrap items-end gap-2 border-t border-gray-100 pt-4">
                        <div className="space-y-1">
                            <Label htmlFor="gm-year">Datos para UI GreenMetric del año</Label>
                            <Input id="gm-year" type="number" min={2025} max={new Date().getFullYear()} value={year} onChange={(e) => setYear(Number(e.target.value))} className="w-28" />
                        </div>
                        <Button variant="outline" disabled={busy || !year} onClick={download}>
                            <FileSpreadsheet className="h-4 w-4 mr-1" /> Descargar Excel
                        </Button>
                        <p className="text-xs text-eco-forest/60 pb-2">Kilos por material y por mes, personas y certificados como evidencia. Solo lo que pasó por Zyrcle.</p>
                    </div>
                    <div>
                        <p className="text-sm font-medium text-eco-forest mb-2">Últimos informes</p>
                        {reporting.data.reports.length === 0 ? (
                            <Empty>Aún no se ha enviado ninguno.</Empty>
                        ) : (
                            <ul className="divide-y divide-gray-100">
                                {reporting.data.reports.map((r) => (
                                    <li key={r.period} className="py-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                                        <span className="font-medium text-eco-forest">{r.period}</span>
                                        <Badge variant={r.status === "sent" ? "default" : r.status === "failed" ? "destructive" : "outline"}>{STATUS[r.status]}</Badge>
                                        <span className="text-eco-forest/70">
                                            {r.status === "sent" ? `a ${r.recipients} ${r.recipients === 1 ? "correo" : "correos"}` : r.last_error ?? ""}
                                        </span>
                                        {r.certificate_id && (
                                            <Link to={`/certificates/${r.certificate_id}`} className="text-eco-emerald font-medium hover:underline">
                                                Certificado
                                            </Link>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>
            )}
        </Section>
    );
}

function ReportingForm({ data }: { data: Reporting }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [monthly, setMonthly] = useState(data.monthly_report);
    const [emails, setEmails] = useState(data.report_emails.join("\n"));
    const [hostGoal, setHostGoal] = useState(data.monthly_goal_kg?.toString() ?? "");
    const [siteGoals, setSiteGoals] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState(false);
    useEffect(() => {
        setSiteGoals(Object.fromEntries(data.sites.map((s) => [s.id, s.monthly_goal_kg?.toString() ?? ""])));
    }, [data.sites]);

    const list = emails.split(/[\s,;]+/).filter(Boolean);
    const goalsOk = validGoal(hostGoal) && Object.values(siteGoals).every(validGoal);
    const save = async () => {
        setSaving(true);
        try {
            await api.setReporting(data.host_id, { monthly_report: monthly, report_emails: list, monthly_goal_kg: goal(hostGoal) });
            for (const s of data.sites) {
                const next = goal(siteGoals[s.id] ?? "");
                if (next !== s.monthly_goal_kg) await api.setSiteGoal(s.id, next);
            }
            toast.success(monthly ? "Guardado: el informe llega el próximo mes" : "Guardado");
            await queryClient.invalidateQueries({ queryKey: ["op", "reporting", data.host_id] });
        } catch (e) {
            failed(e);
        } finally {
            setSaving(false);
        }
    };

    return (
        <form
            className="space-y-4"
            onSubmit={(e) => {
                e.preventDefault();
                save();
            }}
        >
            <div className="flex items-center gap-2">
                <Checkbox id="monthly-report" checked={monthly} onCheckedChange={(v) => setMonthly(v === true)} />
                <Label htmlFor="monthly-report" className="flex items-center gap-1">
                    <Mail className="h-4 w-4 text-eco-emerald" /> Enviar cada mes el certificado del mes anterior
                </Label>
            </div>
            <div className="space-y-1 max-w-xl">
                <Label htmlFor="report-emails">Correos que lo reciben (uno por línea, hasta 10)</Label>
                <Textarea id="report-emails" rows={3} value={emails} onChange={(e) => setEmails(e.target.value)} placeholder="sostenibilidad@universidad.edu.co" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 items-end">
                <div className="space-y-1">
                    <Label htmlFor="host-goal">Meta mensual de la institución (kg)</Label>
                    <Input id="host-goal" inputMode="numeric" value={hostGoal} onChange={(e) => setHostGoal(e.target.value)} placeholder="Sin meta" />
                </div>
                {data.sites.map((s) => (
                    <div key={s.id} className="space-y-1">
                        <Label htmlFor={`goal-${s.id}`}>Meta de {s.name} (kg)</Label>
                        <Input
                            id={`goal-${s.id}`}
                            inputMode="numeric"
                            value={siteGoals[s.id] ?? ""}
                            onChange={(e) => setSiteGoals((g) => ({ ...g, [s.id]: e.target.value }))}
                            placeholder="Sin meta"
                        />
                    </div>
                ))}
            </div>
            <Button type="submit" disabled={saving || !goalsOk || (monthly && list.length === 0)}>
                <Save className="h-4 w-4 mr-1" /> Guardar
            </Button>
        </form>
    );
}
