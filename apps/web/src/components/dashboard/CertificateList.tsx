import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Leaf } from "lucide-react";
import { kg } from "@zyrcle/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

/** A host's impact certificates, newest month first (docs/adr/0027). */
export function CertificateList({ hostId }: { hostId: string }) {
    const { data } = useQuery({ queryKey: ["host-certificates", hostId], queryFn: () => api.hostCertificates(hostId) });
    return (
        <Card className="shadow-sm border-0 rounded-xl bg-white mt-8 max-w-7xl mx-auto">
            <CardHeader className="bg-eco-forest/5 rounded-t-xl">
                <CardTitle className="text-xl text-eco-forest flex items-center gap-2">
                    <Leaf className="h-5 w-5 text-eco-emerald" /> Certificados de impacto
                </CardTitle>
                <CardDescription className="text-eco-forest/70">
                    Cada mes, el material que llegó a un reciclador y el CO₂e que se evitó. Cualquiera puede verificarlos.
                </CardDescription>
            </CardHeader>
            <CardContent className="p-6">
                {!data || data.length === 0 ? (
                    <p className="text-sm text-eco-forest/60 text-center py-4">Aún no hay certificados: llegan cuando se vende el material del mes.</p>
                ) : (
                    <ul className="divide-y divide-gray-100">
                        {data.map((c) => (
                            <li key={c.id} className="py-3 flex flex-wrap items-center justify-between gap-2">
                                <span className="font-medium text-eco-forest">
                                    {c.period}
                                    {c.site ? ` · ${c.site.name}` : ""}
                                </span>
                                <span className="text-sm text-eco-forest/80">
                                    {kg(c.grams / 1000, 2)} recuperados · {kg(c.co2e_g / 1000, 2)} de CO₂e evitado
                                </span>
                                <Link to={`/certificates/${c.id}`} className="text-sm font-medium text-eco-emerald hover:underline">
                                    Ver y verificar
                                </Link>
                            </li>
                        ))}
                    </ul>
                )}
            </CardContent>
        </Card>
    );
}
