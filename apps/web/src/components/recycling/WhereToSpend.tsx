import { Clock, MapPin, Store } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { MerchantListing } from "@zyrcle/client";
import { api } from "@/lib/api";

/** The campus merchants that take ZYR, grouped by institution and campus (docs/adr/0041). */
export function WhereToSpend() {
    const { data, isLoading } = useQuery({ queryKey: ["merchants"], queryFn: api.merchants, staleTime: 60_000 });
    const groups = new Map<string, { title: string; items: MerchantListing[] }>();
    for (const m of data ?? []) {
        const key = `${m.host.id}/${m.site?.id ?? ""}`;
        const title = m.site ? `${m.host.name} · ${m.site.name}` : m.host.name;
        if (!groups.has(key)) groups.set(key, { title, items: [] });
        groups.get(key)!.items.push(m);
    }

    return (
        <Card className="shadow-sm border-0 rounded-xl bg-white max-w-4xl mx-auto">
            <CardHeader>
                <CardTitle className="text-xl text-eco-forest flex items-center">
                    <Store className="h-5 w-5 mr-2 text-eco-emerald" />
                    Dónde gastar
                </CardTitle>
                <CardDescription className="text-eco-forest/70">Estos comercios reciben tus ZYR: 1 ZYR vale 1 peso. Pagas escaneando el QR de su cobro con la app.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {isLoading ? (
                    <p className="text-sm text-eco-forest/60">Cargando…</p>
                ) : groups.size === 0 ? (
                    <p className="text-sm text-eco-forest/60">Todavía no hay comercios en tu campus.</p>
                ) : (
                    [...groups.values()].map((g) => (
                        <section key={g.title} aria-label={g.title}>
                            <h3 className="text-sm font-semibold text-eco-forest/70 mb-2">{g.title}</h3>
                            <ul className="grid gap-3 sm:grid-cols-2">
                                {g.items.map((m) => (
                                    <li key={`${g.title}/${m.name}`} className="rounded-xl border border-gray-100 p-4">
                                        <p className="font-semibold text-eco-forest">{m.name}</p>
                                        {m.offer && <p className="text-sm text-eco-forest/80 mt-0.5">{m.offer}</p>}
                                        <div className="mt-2 space-y-1 text-xs text-eco-forest/60">
                                            {m.place && <p className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" /> {m.place}</p>}
                                            {m.hours && <p className="flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> {m.hours}</p>}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    ))
                )}
            </CardContent>
        </Card>
    );
}
