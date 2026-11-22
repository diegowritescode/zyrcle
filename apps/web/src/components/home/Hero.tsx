import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { kg, pesos } from "@zyrcle/client";
import { api } from "@/lib/api";
import { unsplash } from "@/lib/images";

function impact(kgVerified: number) {
    return kgVerified >= 1000 ? `${(kgVerified / 1000).toLocaleString("es-CO", { maximumFractionDigits: 1 })} t verificadas` : `${kg(kgVerified)} verificados`;
}

export function Hero() {
    // Live platform totals: every figure here comes from verified deposits and on-chain payouts.
    const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: 15_000 });
    const residents = stats?.residents ?? 0;

    return (
        <div className="relative overflow-hidden">
            {/* Background decoration */}
            <div className="absolute inset-0 z-0">
                <div className="absolute top-0 right-0 -translate-y-1/4 translate-x-1/4 w-[600px] h-[600px] rounded-full bg-eco-emerald/10 blur-3xl"></div>
                <div className="absolute bottom-0 left-0 translate-y-1/4 -translate-x-1/4 w-[600px] h-[600px] rounded-full bg-eco-lime/10 blur-3xl"></div>
            </div>

            <div className="container mx-auto px-4 py-20 md:py-28 relative z-10">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
                    <div className="space-y-6">
                        <div className="inline-block px-4 py-1.5 rounded-full bg-eco-forest-light/10 text-eco-forest-dark font-medium text-sm">
                            Reciclaje trazable en Avalanche
                        </div>
                        <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-eco-forest-dark leading-tight">
                            Únete a la <span className="text-eco-emerald">eco-revolución</span> del reciclaje en blockchain
                        </h1>
                        <p className="text-lg text-eco-forest-dark/80 max-w-xl">
                            Contenedores con báscula y sensores verifican lo que depositas, para que nadie cobre por una piedra,
                            y te pagan al instante en ZYR, la moneda de una L1 propia en Avalanche. 1 ZYR = 1 peso.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4">
                            <Button asChild className="bg-eco-emerald text-white hover:bg-eco-emerald/90 rounded-full px-8 h-12">
                                <Link to="/recycling">
                                    Probar la demo
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                            <Button asChild variant="outline" className="border-eco-forest text-eco-forest hover:bg-eco-forest/5 rounded-full px-8 h-12">
                                <a href="#learn-more">Conocer más</a>
                            </Button>
                        </div>
                    </div>

                    <div className="flex justify-center">
                        <div className="relative w-full max-w-md">
                            <div className="rounded-2xl overflow-hidden shadow-xl border border-eco-forest/10">
                                <img
                                    src={unsplash("photo-1523712999610-f77fbcfc3843", 900)}
                                    alt="Bosque con luz entre los árboles"
                                    className="w-full h-[400px] object-cover"
                                />
                                <div className="absolute inset-0 bg-gradient-to-t from-eco-forest/80 to-transparent"></div>
                                <div className="absolute bottom-0 left-0 p-6 text-white">
                                    <p className="text-sm font-medium mb-2">
                                        {residents === 0
                                            ? "Sé la primera persona en reciclar en la demo"
                                            : residents === 1
                                              ? "1 residente ya recicló en la demo"
                                              : `${residents.toLocaleString("es-CO")} residentes ya reciclaron en la demo`}
                                    </p>
                                    <div className="flex -space-x-2">
                                        {Array.from({ length: Math.min(5, residents) }, (_, i) => (
                                            <div key={i} className="w-8 h-8 rounded-full bg-eco-lime-light border-2 border-white"></div>
                                        ))}
                                        {residents > 5 && (
                                            <div className="w-8 h-8 rounded-full bg-eco-emerald flex items-center justify-center text-xs font-bold border-2 border-white">
                                                +{residents - 5}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <div className="absolute -top-6 -right-6 bg-white rounded-xl p-4 shadow-lg border border-eco-forest/10">
                                <div className="flex items-center space-x-3">
                                    <div className="w-10 h-10 rounded-full bg-eco-emerald flex items-center justify-center text-white font-bold" aria-hidden>
                                        🌱
                                    </div>
                                    <div>
                                        <p className="text-xs text-eco-forest/60">Impacto total</p>
                                        <p className="font-semibold text-eco-forest">{stats ? impact(stats.kg_verified) : "—"}</p>
                                    </div>
                                </div>
                            </div>

                            <div className="absolute -bottom-6 -left-6 bg-white rounded-xl p-4 shadow-lg border border-eco-forest/10">
                                <div className="flex items-center space-x-3">
                                    <div className="w-10 h-10 rounded-full bg-eco-lime flex items-center justify-center text-white font-bold" aria-hidden>
                                        💰
                                    </div>
                                    <div>
                                        <p className="text-xs text-eco-forest/60">Recompensas pagadas</p>
                                        <p className="font-semibold text-eco-forest">{stats ? `${pesos(stats.paid_cop)} en ZYR` : "—"}</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
