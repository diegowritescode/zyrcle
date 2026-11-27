import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MATERIALS, kg } from "@zyrcle/client";
import { FileCheck2, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { CertificatePreview } from "@/console/api";
import { useConsole } from "@/console/context";
import { failed } from "@/console/format";
import { API_URL } from "@/lib/config";
import { HostReporting } from "./HostReporting";
import { Empty, Loading, Section, Stat } from "./shared";

const ALL = "all";
const kgOf = (g: number) => kg(g / 1000, 2);
// Last month, in the operator's time zone: certificates close a month that has ended.
const lastMonth = () => {
    const d = new Date();
    d.setDate(0);
    return d.toLocaleDateString("en-CA").slice(0, 7);
};

/** Issue a host's monthly impact certificate (docs/adr/0027). */
export function Certificates() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const hosts = useQuery({ queryKey: ["op", "hosts"], queryFn: api.hosts });
    const sites = useQuery({ queryKey: ["op", "sites"], queryFn: api.sites });
    const list = useQuery({ queryKey: ["op", "certificates"], queryFn: api.certificates, refetchInterval: 10_000 });
    const [hostId, setHostId] = useState("");
    const [siteId, setSiteId] = useState(ALL);
    const [period, setPeriod] = useState(lastMonth);
    const [preview, setPreview] = useState<CertificatePreview | null>(null);
    const [busy, setBusy] = useState(false);

    const site = siteId === ALL ? null : siteId;
    const look = async () => {
        setBusy(true);
        try {
            setPreview(await api.previewCertificate(hostId, site, period));
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };
    const issue = async () => {
        setBusy(true);
        try {
            await api.issueCertificate(hostId, site, period);
            toast.success("Certificado emitido. Su huella se ancla en la cadena en unos segundos.");
            setPreview(null);
            await queryClient.invalidateQueries({ queryKey: ["op", "certificates"] });
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="space-y-6">
            <Section title="Emitir un certificado" description="Cuenta el material vendido en el mes y lo reclama: el mismo gramo no entra en dos certificados">
                <div className="flex flex-wrap items-end gap-2 mb-4">
                    <div className="space-y-1">
                        <Label>Anfitrión</Label>
                        <Select value={hostId} onValueChange={(v) => { setHostId(v); setSiteId(ALL); setPreview(null); }}>
                            <SelectTrigger className="w-56"><SelectValue placeholder="Elige uno" /></SelectTrigger>
                            <SelectContent>
                                {(hosts.data ?? []).map((h) => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1">
                        <Label>Sede</Label>
                        <Select value={siteId} onValueChange={(v) => { setSiteId(v); setPreview(null); }} disabled={!hostId}>
                            <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value={ALL}>Todas las sedes</SelectItem>
                                {(sites.data ?? []).filter((s) => s.host_id === hostId).map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="cert-month">Mes</Label>
                        <Input id="cert-month" type="month" value={period} onChange={(e) => { setPeriod(e.target.value); setPreview(null); }} className="w-44" />
                    </div>
                    <Button variant="outline" disabled={busy || !hostId || !period} onClick={look}>
                        <Search className="h-4 w-4 mr-1" /> Ver qué entra
                    </Button>
                </div>
                {preview && (
                    preview.deposits === 0 ? (
                        <Empty>No hay material vendido sin certificar en ese mes.</Empty>
                    ) : (
                        <div className="space-y-3">
                            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                                <Stat label="Material vendido" value={kgOf(preview.grams)} />
                                <Stat label="CO₂e evitado" value={kgOf(preview.co2e_g)} hint="EPA WARM v16, frente a relleno" />
                                <Stat label="Depósitos" value={preview.deposits} />
                                <Stat label="Personas" value={preview.participants} />
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {Object.entries(preview.by_material).map(([m, v]) => (
                                    <Badge key={m} variant="outline">{MATERIALS[m] ?? m}: {kgOf(v.grams)} · {kgOf(v.co2e_g)} CO₂e</Badge>
                                ))}
                            </div>
                            <Button disabled={busy} onClick={issue}>
                                <FileCheck2 className="h-4 w-4 mr-1" /> Emitir certificado
                            </Button>
                        </div>
                    )
                )}
            </Section>
            <HostReporting />
            <Section title="Certificados emitidos">
                {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>Aún no hay certificados.</Empty> : (
                    <ul className="divide-y divide-gray-100">
                        {list.data.map((c) => (
                            <li key={c.id} className="py-3 flex flex-wrap items-center justify-between gap-2">
                                <span className="font-medium text-eco-forest">{c.host.name}{c.site ? ` · ${c.site.name}` : ""} · {c.period}</span>
                                <span className="text-sm text-eco-forest/80">{kgOf(c.grams)} · {kgOf(c.co2e_g)} CO₂e · {c.deposits} depósitos</span>
                                <Badge variant={c.status === "anchored" ? "default" : "outline"}>{c.status === "anchored" ? "Anclado" : c.status === "issued" ? "Anclando…" : "Error"}</Badge>
                                <span className="flex gap-3">
                                    <Link to={`/certificates/${c.id}`} className="text-sm font-medium text-eco-emerald hover:underline">Ver</Link>
                                    <a href={`${API_URL}/v1/certificates/${c.id}/pdf`} target="_blank" rel="noreferrer" className="text-sm font-medium text-eco-emerald hover:underline">PDF</a>
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </Section>
        </div>
    );
}
