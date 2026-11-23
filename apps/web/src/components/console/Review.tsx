import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MATERIALS, dateTime, grams, type Session } from "@zyrcle/client";
import { Check, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useConsole } from "@/console/context";
import { Empty, Loading, Section } from "./shared";
import { failed } from "@/console/format";

/** What the verification flagged, in words. */
const REASONS: [RegExp, string][] = [
    [/metal detected/, "El sensor detectó metal en un material que no es metal"],
    [/metal sensor saw none/, "Se declaró metal pero el sensor no vio metal"],
    [/density|g\/ml/, "Demasiado pesado para su volumen (¿piedras o agua?)"],
    [/camera saw/, "La cámara vio otro material"],
];
const explain = (reason: string) => REASONS.find(([re]) => re.test(reason))?.[1] ?? reason;

/** Deposits the verification was not sure about: approve (it gets paid) or reject. */
export function Review() {
    const { api } = useConsole();
    const queue = useQuery({ queryKey: ["op", "review"], queryFn: api.reviewQueue, refetchInterval: 10_000 });

    return (
        <Section title="Depósitos en revisión" description="Nunca se rechaza un depósito en silencio: decide tú y deja una nota">
            {!queue.data ? <Loading /> : queue.data.length === 0 ? <Empty>No hay depósitos esperando revisión.</Empty> : (
                <div className="space-y-3">
                    {queue.data.map((s) => (
                        <ReviewRow key={s.id} session={s} />
                    ))}
                </div>
            )}
        </Section>
    );
}

function ReviewRow({ session: s }: { session: Session }) {
    const { api } = useConsole();
    const queryClient = useQueryClient();
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const decide = async (approve: boolean) => {
        setBusy(true);
        try {
            await api.review(s.id, approve, note);
            toast.success(approve ? "Aprobado: se pagará su anticipo" : "Rechazado");
            await queryClient.invalidateQueries({ queryKey: ["op"] });
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="rounded-xl border border-gray-100 p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2 justify-between">
                <p className="font-semibold text-eco-forest">
                    {MATERIALS[s.declared_material] ?? s.declared_material} · {s.deposited_g === null ? "—" : grams(s.deposited_g)} · {s.container_id}
                </p>
                <span className="text-xs text-eco-forest/60">{dateTime(s.updated_at)}</span>
            </div>
            <div className="flex flex-wrap gap-2">
                {s.reasons.map((r) => (
                    <Badge key={r} variant="outline" className="border-amber-300 text-amber-800 bg-amber-50">
                        {explain(r)}
                    </Badge>
                ))}
                {s.score !== null && <Badge variant="outline">Confianza {Math.round(s.score * 100)} %</Badge>}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
                <Input placeholder="Nota (opcional)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Nota de la revisión" />
                <div className="flex gap-2">
                    <Button disabled={busy} onClick={() => decide(true)}>
                        <Check className="h-4 w-4 mr-1" /> Aprobar
                    </Button>
                    <Button variant="outline" disabled={busy} onClick={() => decide(false)}>
                        <X className="h-4 w-4 mr-1" /> Rechazar
                    </Button>
                </div>
            </div>
        </div>
    );
}
