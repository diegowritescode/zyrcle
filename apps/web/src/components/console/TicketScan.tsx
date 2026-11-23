import { useState } from "react";
import { MATERIALS, pesos } from "@zyrcle/client";
import { AlertTriangle, Camera, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { OperatorApiError, type TicketScan as Scan } from "@/console/api";
import { useConsole } from "@/console/context";
import { photoToJpeg } from "@/console/photo";
import { Section } from "./shared";

const kg = (v: number | null) => (v === null ? "—" : `${v.toLocaleString("es-CO", { maximumFractionDigits: 2 })} kg`);
const cop = (v: number | null) => (v === null ? "—" : pesos(Math.round(v)));

/** Read the collection center's scale ticket from a photo (docs/adr/0038). The model reads, the API
 * checks the arithmetic and proposes the bags, and the operator decides what goes into the sale. */
export function TicketScanCard({ onUse }: { onUse: (scan: Scan) => void }) {
    const { api } = useConsole();
    const [preview, setPreview] = useState<string | null>(null);
    const [photo, setPhoto] = useState<string | null>(null);
    const [scan, setScan] = useState<Scan | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const pick = async (file: File | undefined) => {
        setScan(null);
        setError(null);
        if (!file) return;
        try {
            const jpeg = await photoToJpeg(file);
            setPhoto(jpeg.base64);
            setPreview(jpeg.previewUrl);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };
    const read = async () => {
        if (!photo) return;
        setBusy(true);
        setError(null);
        try {
            setScan(await api.scanTicket(photo, "image/jpeg"));
        } catch (e) {
            setError(
                e instanceof OperatorApiError && e.status === 503
                    ? "La lectura con IA está apagada: falta la llave de Anthropic en el servidor."
                    : e instanceof Error ? e.message : String(e),
            );
        } finally {
            setBusy(false);
        }
    };
    const r = scan?.reading;

    return (
        <Section title="Leer el tiquete con una foto" description="Toma la foto del tiquete del centro de acopio. La IA lo lee, revisamos las cuentas y te proponemos las bolsas; tú revisas todo antes de registrar la venta">
            <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1">
                    <Label htmlFor="ticket-photo">Foto del tiquete</Label>
                    <Input id="ticket-photo" type="file" accept="image/*" capture="environment" onChange={(e) => pick(e.target.files?.[0])} className="max-w-xs" />
                </div>
                <Button onClick={read} disabled={!photo || busy}>
                    {busy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Sparkles className="h-4 w-4 mr-1" />}
                    {busy ? "Leyendo… tarda unos segundos" : "Leer tiquete"}
                </Button>
            </div>
            {error && <p className="text-sm text-red-700 mt-3">{error}</p>}
            {(preview || scan) && (
                <div className="mt-4 grid gap-4 md:grid-cols-[200px_1fr]">
                    {preview && <img src={preview} alt="Foto del tiquete" className="rounded-lg border border-eco-forest/10 max-h-64 object-contain" />}
                    {scan?.status === "failed" && <p className="text-sm text-red-700">No se pudo leer: {scan.error}</p>}
                    {r && (
                        <div className="space-y-3 min-w-0">
                            <p className="text-sm text-eco-forest">
                                {r.center_name ?? "Centro sin leer"} · tiquete {r.ticket_ref ?? "—"} · {r.date ?? "sin fecha"} · total {cop(r.total_cop)}
                            </p>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>En el tiquete</TableHead>
                                        <TableHead>Material</TableHead>
                                        <TableHead>Peso</TableHead>
                                        <TableHead>Precio</TableHead>
                                        <TableHead>Valor</TableHead>
                                        <TableHead>Bolsa propuesta</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {r.lines.map((l, i) => (
                                        <TableRow key={i}>
                                            <TableCell>{l.label}</TableCell>
                                            <TableCell>{MATERIALS[l.material] ?? l.material}</TableCell>
                                            <TableCell>{kg(l.kg)}</TableCell>
                                            <TableCell>{cop(l.cop_per_kg)}</TableCell>
                                            <TableCell>{cop(l.amount_cop)}</TableCell>
                                            <TableCell className="font-mono">{scan.proposed_bags[i] ?? "—"}</TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                            {scan.checks.length > 0 && (
                                <ul className="space-y-1" aria-label="Revisa esto">
                                    {scan.checks.map((c, i) => (
                                        <li key={i} className="text-sm text-amber-800 flex items-start gap-2">
                                            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" /> {c.detail}
                                        </li>
                                    ))}
                                </ul>
                            )}
                            <Button variant="outline" onClick={() => onUse(scan)}>
                                <Camera className="h-4 w-4 mr-1" /> Usar en la venta
                            </Button>
                        </div>
                    )}
                </div>
            )}
        </Section>
    );
}
