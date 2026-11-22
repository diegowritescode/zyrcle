import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Recycle, WifiOff } from "lucide-react";
import { ContainerQr } from "@/components/recycling/ContainerQr";
import { StatusPill } from "@/components/recycling/StatusPill";
import { api } from "@/lib/api";
import { MATERIALS, familyOf } from "@/lib/labels";
import { manualCode, parseContainerQr } from "@/lib/qr";

/**
 * What the container's own screen shows: a QR whose code rotates every 30 s, so only someone
 * standing in front of it can open the lid. Simulated here for the demo containers; open it on a
 * laptop and scan it with the phone from /recycling.
 */
const ContainerScreen = () => {
    const { containerId = "" } = useParams();
    const { data: containers, isLoading } = useQuery({
        queryKey: ["demo-containers"],
        queryFn: api.demo.containers,
        refetchInterval: 2_000,
    });
    const container = containers?.find((c) => c.id === containerId);
    const parsed = container?.qr ? parseContainerQr(container.qr) : null;

    return (
        <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-eco-lime/10 via-white to-eco-emerald/10 p-4">
            <div className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-eco-forest/10 p-8 text-center space-y-6">
                <div className="flex items-center justify-center space-x-2">
                    <img src="/favicon.svg" alt="" className="h-10 w-10" />
                    <span className="text-xl font-bold text-eco-forest">ZYRCLE</span>
                </div>

                {isLoading ? (
                    <Loader2 className="h-10 w-10 mx-auto animate-spin text-eco-emerald" />
                ) : !container ? (
                    <p className="text-eco-forest/70">
                        No existe un contenedor de la demo con el código <code>{containerId}</code>.
                    </p>
                ) : (
                    <>
                        <div>
                            <h1 className="text-2xl font-bold text-eco-forest flex items-center justify-center">
                                <Recycle className={`h-7 w-7 mr-2 ${familyOf(container.accepted_materials).icon}`} />
                                {container.name}
                            </h1>
                            <p className="text-sm text-eco-forest/60 mt-1">
                                Recibe {container.accepted_materials.map((m) => MATERIALS[m] ?? m).join(", ")}
                            </p>
                        </div>
                        <div className="flex justify-center">
                            <StatusPill online={container.online} busy={container.busy} />
                        </div>
                        {container.busy ? (
                            <p className="text-lg text-eco-forest py-16">Alguien está reciclando. Espera tu turno.</p>
                        ) : container.qr && parsed ? (
                            <>
                                <div className="flex justify-center">
                                    <ContainerQr value={container.qr} size={280} className="border-4 border-eco-emerald/30 p-2" />
                                </div>
                                <div>
                                    <p className="text-xs text-eco-forest/60">¿Sin cámara? Escribe este código</p>
                                    <p className="text-xl font-mono font-semibold tracking-wider text-eco-forest">
                                        {manualCode(parsed.containerId, parsed.code)}
                                    </p>
                                </div>
                                <p className="text-sm text-eco-forest/70">
                                    Escanéalo desde <strong>Reciclar</strong> en la app. El código cambia cada 30 segundos.
                                </p>
                            </>
                        ) : (
                            <div className="py-16 text-eco-forest/60 flex flex-col items-center gap-2">
                                <WifiOff className="h-8 w-8" />
                                {container.online ? "Generando código…" : "Sin conexión"}
                            </div>
                        )}
                    </>
                )}

                <p className="text-xs text-eco-forest/50">
                    Pantalla simulada · <Link to="/recycling" className="underline hover:text-eco-emerald">ir a Reciclar</Link>
                </p>
            </div>
        </main>
    );
};

export default ContainerScreen;
