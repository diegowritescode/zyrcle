import { useState } from "react";
import { ChevronDown, History as HistoryIcon, Recycle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { dateTime, grams, pesos, currentStep, stepLine, CREDITED, MATERIALS, PAYOUT_STATUS, STATES, familyOf, type HistoryEntry } from "@zyrcle/client";
import { api } from "@/lib/api";
import { DepositSteps } from "./DepositSteps";

/** The resident's own deposits, what each one paid, and where each one is now (docs/adr/0041). */
export function History({ token }: { token: string | null }) {
    const { data: me, isLoading } = useQuery({
        queryKey: ["me", token],
        queryFn: () => api.me(token as string),
        enabled: token !== null,
        refetchInterval: 10_000,
    });
    const sessions = me?.sessions ?? [];

    return (
        <Card className="shadow-sm border-0 rounded-xl bg-white max-w-4xl mx-auto">
            <CardHeader>
                <CardTitle className="text-xl text-eco-forest flex items-center">
                    <HistoryIcon className="h-5 w-5 mr-2 text-eco-emerald" />
                    Mis depósitos
                </CardTitle>
                <CardDescription className="text-eco-forest/70">Tus últimos 20 depósitos con esta wallet. Toca uno para ver por dónde va.</CardDescription>
            </CardHeader>
            <CardContent>
                {token === null || isLoading ? (
                    <p className="text-sm text-eco-forest/60">Cargando…</p>
                ) : sessions.length === 0 ? (
                    <p className="text-sm text-eco-forest/60">Todavía no has reciclado con esta wallet.</p>
                ) : (
                    <ul className="divide-y divide-eco-forest/10">
                        {sessions.map((s) => <DepositRow key={s.id} s={s} />)}
                    </ul>
                )}
            </CardContent>
        </Card>
    );
}

function DepositRow({ s }: { s: HistoryEntry }) {
    const [open, setOpen] = useState(false);
    const steps = s.steps ?? [];
    const now = currentStep(steps);
    const where = now ? stepLine(now, s).title : null;
    const advance = s.payout?.status === "confirmed" ? s.payout.amount_cop : 0;
    const material = MATERIALS[s.declared_material] ?? s.declared_material;

    const row = (
        <>
            <Recycle className={`h-5 w-5 shrink-0 ${familyOf([s.declared_material]).icon}`} />
            <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-eco-forest truncate">
                    {material}
                    {s.deposited_g !== null && ` · ${grams(s.deposited_g)}`}
                    <span className="font-normal text-eco-forest/60"> · {s.container_name}</span>
                </p>
                <p className="text-xs text-eco-forest/60">
                    {dateTime(s.created_at)}
                    {where && <span className="text-eco-emerald font-medium"> · {where}</span>}
                </p>
            </div>
            <div className="text-right">
                {s.payout ? (
                    <>
                        <p className="text-sm font-semibold text-eco-emerald">{pesos(advance + (s.settled_cop ?? 0))}</p>
                        <p className="text-xs text-eco-forest/60">
                            {s.settled_cop ? "Anticipo + venta" : (PAYOUT_STATUS[s.payout.status] ?? s.payout.status)}
                        </p>
                    </>
                ) : (
                    <p className={`text-xs font-medium ${CREDITED.has(s.state) ? "text-eco-emerald" : "text-eco-forest/60"}`}>{STATES[s.state] ?? s.state}</p>
                )}
            </div>
        </>
    );

    if (steps.length === 0) return <li className="py-3 flex items-center gap-3">{row}</li>;
    return (
        <li className="py-3">
            <button
                type="button"
                className="w-full flex items-center gap-3 text-left"
                aria-expanded={open}
                aria-label={`Recorrido de ${material} en ${s.container_name}, ${dateTime(s.created_at)}`}
                onClick={() => setOpen((o) => !o)}
            >
                {row}
                <ChevronDown className={`h-4 w-4 shrink-0 text-eco-forest/40 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
            {open && <DepositSteps entry={s} />}
        </li>
    );
}
