import { CheckCircle, Clock, Info, Loader2, RotateCcw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { type PayoutInfo, type Session, grams, pesos, shortHex, CREDITED, MATERIALS, PAYOUT_STATUS, STATES } from "@zyrcle/client";

/** What the verification said about the deposit and where its payment is. */
export function ResultPanel({ session, payout, onAgain }: { session: Session; payout: PayoutInfo | null; onAgain: () => void }) {
    const credited = CREDITED.has(session.state);
    const Icon = credited ? CheckCircle : session.state === "review" ? Clock : session.state === "rejected" ? XCircle : Info;
    const tone = credited ? "text-eco-emerald" : session.state === "rejected" ? "text-red-500" : "text-amber-500";

    return (
        <div className="text-center space-y-6 animate-in fade-in duration-300">
            <Icon className={`h-16 w-16 mx-auto ${tone}`} />
            <div>
                <p className="text-2xl font-bold text-eco-forest">{STATES[session.state] ?? session.state}</p>
                <p className="text-sm text-eco-forest/70 mt-1">
                    {MATERIALS[session.declared_material] ?? session.declared_material}
                    {session.deposited_g !== null && ` · ${grams(session.deposited_g)}`}
                    {session.score !== null && ` · confianza ${Math.round(session.score * 100)} %`}
                </p>
            </div>

            {credited && (
                <div className="rounded-xl bg-gradient-to-br from-eco-emerald/80 to-eco-forest/80 text-white p-6 text-left">
                    <p className="text-sm text-white/90">Anticipo</p>
                    <p className="text-3xl font-bold mt-1">{payout ? pesos(payout.amount_cop) : "Calculando…"}</p>
                    <p className="text-sm text-white/90 mt-2 flex items-center gap-2">
                        {payout && payout.status !== "confirmed" && payout.status !== "failed" && payout.status !== "deferred" && (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        )}
                        {payout ? PAYOUT_STATUS[payout.status] ?? payout.status : "En cola para pagarse en la cadena"}
                        {payout?.tx_hash && (
                            <code className="text-xs bg-white/15 rounded px-2 py-0.5" title={payout.tx_hash}>
                                tx {shortHex(payout.tx_hash)}
                            </code>
                        )}
                    </p>
                    <p className="text-xs text-white/80 mt-3">
                        Es un anticipo de hasta la mitad del valor estimado de tu material. El resto llega cuando se vende al centro de acopio.
                    </p>
                </div>
            )}

            {session.state === "review" && (
                <p className="text-sm text-eco-forest/70 bg-amber-50 p-3 rounded-lg">
                    Algo no cuadró entre el peso y el volumen. Una persona revisa este depósito antes de pagarlo.
                </p>
            )}
            {session.state === "rejected" && (
                <p className="text-sm text-red-700 bg-red-50 p-3 rounded-lg">Este depósito no se pagará.</p>
            )}
            {session.state === "empty" && (
                <p className="text-sm text-eco-forest/70 bg-eco-forest/5 p-3 rounded-lg">La báscula no registró material: no hay pago.</p>
            )}
            {(session.state === "expired" || session.state === "failed") && (
                <p className="text-sm text-eco-forest/70 bg-eco-forest/5 p-3 rounded-lg">
                    El contenedor no respondió a tiempo. No se cobró nada; vuelve a intentarlo.
                </p>
            )}

            {session.reasons.length > 0 && (
                <details className="text-left text-sm text-eco-forest/70">
                    <summary className="cursor-pointer text-eco-forest">Detalle de la verificación</summary>
                    <ul className="list-disc pl-5 mt-2 space-y-1">
                        {session.reasons.map((r) => (
                            <li key={r}>{r}</li>
                        ))}
                    </ul>
                </details>
            )}

            <Button onClick={onAgain} variant="outline" className="w-full text-eco-forest hover:bg-eco-forest/10">
                <RotateCcw className="h-4 w-4 mr-2" />
                Reciclar otra vez
            </Button>
        </div>
    );
}
