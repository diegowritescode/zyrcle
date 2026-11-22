import { CheckCircle, Loader2, Recycle, Weight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Tooltip as UITooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { type ContainerInfo, type Session, grams, ITEMS, LID_OPEN, MATERIALS, STATES } from "@zyrcle/client";
import { api } from "@/lib/api";

interface Props {
    session: Session;
    container: ContainerInfo | null;
    weight: number | null;
    busy: boolean;
    onDrop: (item: string) => void;
    onFinish: () => void;
}

/** The lid is open: live weight, the demo's "what you throw in" buttons, and "Terminé". */
export function SessionPanel({ session, container, weight, busy, onDrop, onFinish }: Props) {
    const lidOpen = LID_OPEN.has(session.state);
    const { data: items } = useQuery({ queryKey: ["demo-items"], queryFn: api.demo.items, staleTime: Infinity });
    const added = weight !== null && session.tare_g !== null ? Math.max(0, weight - session.tare_g) : null;

    return (
        <div className="text-center space-y-6 animate-in fade-in duration-300">
            {lidOpen ? (
                <Recycle className="h-16 w-16 mx-auto text-eco-emerald" />
            ) : (
                <Loader2 className="h-16 w-16 mx-auto text-eco-emerald animate-spin" />
            )}
            <div>
                <p className="text-lg font-semibold text-eco-forest">
                    {lidOpen ? `Tapa abierta en ${container?.name ?? "el contenedor"}` : STATES[session.state] ?? session.state}
                </p>
                <p className="text-sm text-eco-forest/70 mt-1">
                    Material declarado: {MATERIALS[session.declared_material] ?? session.declared_material}
                    {lidOpen && ` · ${STATES[session.state]}`}
                </p>
            </div>

            <div className="inline-flex items-center gap-3 rounded-xl bg-eco-forest/5 px-6 py-4">
                <Weight className="h-6 w-6 text-eco-emerald" />
                <div className="text-left">
                    <p className="text-xs text-eco-forest/70">Llevas depositado</p>
                    <p className="text-3xl font-bold text-eco-forest tabular-nums" aria-live="polite">
                        {added === null ? "—" : grams(added)}
                    </p>
                </div>
            </div>

            {lidOpen && (
                <>
                    <div className="text-left space-y-3">
                        <p className="text-sm font-medium text-eco-forest">
                            Simula lo que tiras <span className="font-normal text-eco-forest/60">(en un contenedor real, lo tiras y ya)</span>
                        </p>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                            {(items ?? []).map((item) => (
                                <Button
                                    key={item.name}
                                    variant="outline"
                                    onClick={() => onDrop(item.name)}
                                    className={`h-auto py-3 flex flex-col items-center gap-1 whitespace-normal text-eco-forest hover:bg-eco-forest/10 ${item.name === "stone" || item.name === "full_water_bottle" ? "border-amber-300 bg-amber-50/50" : ""}`}
                                >
                                    <span className="text-sm leading-tight">{ITEMS[item.name] ?? item.label}</span>
                                    <span className="text-xs text-eco-forest/60">{grams(item.weight_g)}</span>
                                </Button>
                            ))}
                        </div>
                    </div>
                    <p className="text-sm text-eco-forest/60">Estás ayudando al planeta, y cada kilo verificado se paga.</p>
                    <UITooltip>
                        <TooltipTrigger asChild>
                            <Button
                                onClick={onFinish}
                                disabled={busy}
                                className="w-full bg-eco-emerald text-white hover:bg-eco-emerald/90 hover:scale-105 transition-transform duration-200"
                            >
                                <CheckCircle className="h-4 w-4 mr-2" />
                                Terminé
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent>Cierra el contenedor: pesa, verifica y te paga</TooltipContent>
                    </UITooltip>
                    <p className="text-xs text-eco-forest/60">
                        Si te vas sin tocar «Terminé», el contenedor se cierra solo al minuto y te paga igual.
                    </p>
                </>
            )}
        </div>
    );
}
