import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { pesos } from "@zyrcle/client";
import { Landmark, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { BankProposal } from "@/console/api";
import { useConsole } from "@/console/context";
import { failed } from "@/console/format";
import { Section } from "./shared";

const toBase64 = (file: File) =>
    new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
        reader.onerror = () => reject(new Error("No pudimos leer el archivo."));
        reader.readAsDataURL(file);
    });

/** Match the bank statement to sales and redemptions (docs/adr/0039). The API proposes; the
 * operator confirms each match with one click, as if confirming it by hand. */
export function BankStatementCard() {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const proposals = useQuery({ queryKey: ["op", "bank-proposals"], queryFn: api.bankProposals, refetchInterval: 20_000 });
    const [busy, setBusy] = useState(false);
    const [summary, setSummary] = useState<string | null>(null);

    const upload = async (file: File | undefined) => {
        if (!file) return;
        setBusy(true);
        try {
            const r = await api.uploadStatement(file.name, await toBase64(file));
            setSummary(`${r.movements} movimientos: ${r.added} nuevos, ${r.already_known} ya conocidos.`);
            queryClient.setQueryData(["op", "bank-proposals"], r.proposals);
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };
    const confirm = async (p: BankProposal) => {
        try {
            await api.matchBankLine(p.line.id, p.kind, p.target_id);
            toast.success(p.kind === "sale" ? `Venta ${p.target.ticket_ref} confirmada con el banco` : `Cambio de ${p.target.merchant} pagado`);
            await queryClient.invalidateQueries({ queryKey: ["op"] });
        } catch (e) {
            failed(e);
        }
    };

    return (
        <Section title="Conciliar con el extracto del banco" description="Sube el extracto que descargas del banco (CSV o Excel). Te proponemos qué movimiento paga cada venta o cada cambio a pesos; tú confirmas">
            <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1">
                    <Label htmlFor="bank-file">Extracto del banco</Label>
                    <Input id="bank-file" type="file" accept=".csv,.xlsx,text/csv" onChange={(e) => upload(e.target.files?.[0])} className="max-w-xs" disabled={busy} />
                </div>
                {busy && <Loader2 className="h-5 w-5 animate-spin text-eco-emerald" aria-label="Leyendo el extracto" />}
            </div>
            {summary && <p className="text-sm text-eco-forest/70 mt-2">{summary}</p>}
            {(proposals.data ?? []).length > 0 && (
                <Table className="mt-4">
                    <TableHeader>
                        <TableRow>
                            <TableHead>Movimiento</TableHead>
                            <TableHead>Paga</TableHead>
                            <TableHead>Por qué</TableHead>
                            <TableHead />
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {(proposals.data ?? []).map((p) => (
                            <TableRow key={p.line.id}>
                                <TableCell>
                                    <p className="font-medium">{pesos(Math.abs(p.line.amount_cop))} {p.line.amount_cop < 0 ? "salió" : "entró"} el {p.line.posted_on}</p>
                                    <p className="text-xs text-eco-forest/60">{p.line.description} {p.line.reference && `· ${p.line.reference}`}</p>
                                </TableCell>
                                <TableCell>{p.kind === "sale" ? `Venta ${p.target.ticket_ref} · ${p.target.buyer}` : `Cambio a pesos · ${p.target.merchant}`}</TableCell>
                                <TableCell className="text-xs text-eco-forest/70">{p.why.join(", ")}</TableCell>
                                <TableCell className="text-right">
                                    <Button size="sm" onClick={() => confirm(p)}>
                                        <Landmark className="h-4 w-4 mr-1" /> Confirmar
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
