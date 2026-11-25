import { useState } from "react";
import { Leaf } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { co2e, grams, monthLabel, MATERIALS } from "@zyrcle/client";
import { api } from "@/lib/api";

/** The participant's own impact (docs/adr/0041): what they recycled, what was sold, and the CO2e
 * avoided by what was sold, with the certificates' factors (docs/adr/0027). */
export function Impact({ token }: { token: string | null }) {
    const { data } = useQuery({ queryKey: ["impact", token], queryFn: () => api.impact(token as string), enabled: token !== null, refetchInterval: 60_000 });
    const [hover, setHover] = useState<number | null>(null);
    if (!data || data.deposits === 0) return null;
    const top = Math.max(1, ...data.months.map((m) => m.verified_g));
    const shown = hover !== null ? data.months[hover] : null;

    return (
        <Card className="shadow-sm border-0 rounded-xl bg-white max-w-4xl mx-auto mb-6">
            <CardHeader>
                <CardTitle className="text-xl text-eco-forest flex items-center">
                    <Leaf className="h-5 w-5 mr-2 text-eco-emerald" />
                    Mi impacto
                </CardTitle>
                <CardDescription className="text-eco-forest/70">
                    El CO2e cuenta solo lo que ya se vendió, con los mismos factores de los certificados (EPA WARM v16). Es una cifra indicativa, no un crédito de carbono.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                <dl className="grid grid-cols-3 gap-3">
                    <Stat label="Reciclado y verificado" value={grams(data.totals.verified_g)} />
                    <Stat label="Ya vendido" value={grams(data.totals.sold_g)} />
                    <Stat label="CO2e evitado" value={co2e(data.totals.co2e_g)} />
                </dl>

                <div>
                    <p className="text-sm font-medium text-eco-forest">Reciclado por mes</p>
                    <p className="text-xs text-eco-forest/60 h-4" aria-live="polite">
                        {shown ? `${monthLabel(shown.month)}: ${grams(shown.verified_g)} verificados · ${grams(shown.sold_g)} vendidos · ${co2e(shown.co2e_g)} de CO2e` : "Pasa el cursor por un mes para ver sus cifras."}
                    </p>
                    <div className="mt-2 flex items-end gap-[2px] h-24 border-b border-eco-forest/15" role="list" aria-label="Gramos verificados por mes">
                        {data.months.map((m, i) => (
                            <div
                                key={m.month}
                                role="listitem"
                                aria-label={`${monthLabel(m.month)}: ${grams(m.verified_g)} verificados, ${grams(m.sold_g)} vendidos`}
                                className="flex-1 h-full flex items-end cursor-default"
                                onMouseEnter={() => setHover(i)}
                                onMouseLeave={() => setHover(null)}
                            >
                                <div
                                    className={`w-full rounded-t-[4px] ${hover === i ? "bg-eco-forest" : "bg-eco-emerald"}`}
                                    style={{ height: m.verified_g ? `${Math.max(4, (100 * m.verified_g) / top)}%` : 0 }}
                                />
                            </div>
                        ))}
                    </div>
                    <div className="mt-1 flex gap-[2px] text-[10px] text-eco-forest/50">
                        {data.months.map((m, i) => (
                            <span key={m.month} className="flex-1 text-center">{i % 3 === 0 || i === data.months.length - 1 ? monthLabel(m.month).split(" ")[0] : ""}</span>
                        ))}
                    </div>
                </div>

                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-left text-xs text-eco-forest/60">
                            <th className="font-normal pb-1">Material</th>
                            <th className="font-normal pb-1 text-right">Verificado</th>
                            <th className="font-normal pb-1 text-right">Vendido</th>
                            <th className="font-normal pb-1 text-right">CO2e evitado</th>
                        </tr>
                    </thead>
                    <tbody className="text-eco-forest">
                        {data.materials.map((m) => (
                            <tr key={m.material} className="border-t border-eco-forest/10">
                                <td className="py-1.5">{MATERIALS[m.material] ?? m.material}</td>
                                <td className="py-1.5 text-right">{grams(m.verified_g)}</td>
                                <td className="py-1.5 text-right">{grams(m.sold_g)}</td>
                                <td className="py-1.5 text-right">{co2e(m.co2e_g)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </CardContent>
        </Card>
    );
}

function Stat({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-xl bg-eco-forest/5 px-3 py-3">
            <dt className="text-xs text-eco-forest/60">{label}</dt>
            <dd className="text-lg font-semibold text-eco-forest">{value}</dd>
        </div>
    );
}
