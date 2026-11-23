import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, grams } from "@zyrcle/client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { type Incident } from "@/console/api";
import { useConsole } from "@/console/context";
import { Empty, Loading, Section } from "./shared";
import { failed, signedGrams } from "@/console/format";

const KIND: Record<Incident["kind"], { title: string; what: string }> = {
    container_balance: {
        title: "El contenedor no cuadra al abrirlo",
        what: "Pesaba distinto de lo que dejó la recolección anterior más lo que entró en los depósitos: algo entró o salió por fuera de una sesión.",
    },
    collection_balance: {
        title: "Salió material sin pesarse",
        what: "Lo que salió del contenedor no coincide con lo pesado en bolsas y residuo.",
    },
    bag_balance: {
        title: "El comprador pesó distinto la bolsa",
        what: "El peso del tiquete no coincide con el de la bolsa, más allá de la humedad y las etiquetas.",
    },
};

/** Mass balances that did not hold (docs/adr/0012). The bags they name are not sold or settled
 * until an operator resolves them with a note. */
export function Incidents() {
    const { api } = useConsole();
    const [showResolved, setShowResolved] = useState(false);
    const list = useQuery({
        queryKey: ["op", "incidents", showResolved ? "resolved" : "open"],
        queryFn: () => api.incidents(showResolved ? "resolved" : "open"),
        refetchInterval: 15_000,
    });

    return (
        <Section
            title="Incidentes"
            description="Un balance de masa que no cuadró. Sus bolsas no se venden hasta que lo resuelvas"
            actions={
                <Button variant="outline" size="sm" onClick={() => setShowResolved((v) => !v)}>
                    {showResolved ? "Ver abiertos" : "Ver resueltos"}
                </Button>
            }
        >
            {!list.data ? <Loading /> : list.data.length === 0 ? <Empty>{showResolved ? "Aún no hay incidentes resueltos." : "Todo cuadra: no hay incidentes abiertos."}</Empty> : (
                <div className="space-y-3">
                    {list.data.map((i) => (
                        <IncidentRow key={i.id} incident={i} />
                    ))}
                </div>
            )}
        </Section>
    );
}

function IncidentRow({ incident: i }: { incident: Incident }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const resolve = async () => {
        setBusy(true);
        try {
            await api.resolveIncident(i.id, note);
            toast.success("Incidente resuelto: sus bolsas pueden seguir");
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
                <p className="font-semibold text-eco-forest">{KIND[i.kind].title}</p>
                <span className="text-xs text-eco-forest/60">{dateTime(i.created_at)}</span>
            </div>
            <p className="text-sm text-eco-forest/80">{KIND[i.kind].what}</p>
            <div className="flex flex-wrap gap-2 text-sm">
                <Badge variant="outline">Esperado {grams(Math.max(i.expected_g, 0))}</Badge>
                <Badge variant="outline">Medido {grams(Math.max(i.measured_g, 0))}</Badge>
                <Badge variant="destructive">{signedGrams(i.difference_g)}</Badge>
                {i.container_id && <Badge variant="outline">{i.container_id}</Badge>}
                {i.bag_ids.length > 0 && <Badge variant="outline">{i.bag_ids.length} bolsa(s) frenada(s)</Badge>}
            </div>
            {i.status === "open" ? (
                <div className="space-y-2 pt-1">
                    <Textarea placeholder="Qué pasó y qué decidiste (queda registrado con tu nombre)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Nota de resolución" />
                    <Button disabled={busy || !note.trim()} onClick={resolve}>
                        Resolver
                    </Button>
                </div>
            ) : (
                <p className="text-sm text-eco-forest/70">
                    Resuelto por {i.resolved_by}: {i.resolution_note}
                </p>
            )}
        </div>
    );
}
