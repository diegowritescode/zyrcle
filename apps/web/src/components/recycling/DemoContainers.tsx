import { ExternalLink, MonitorSmartphone, Recycle } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { MATERIALS, familyOf } from "@/lib/labels";
import { ContainerQr } from "./ContainerQr";
import { StatusPill } from "./StatusPill";

/**
 * The demo's simulated containers, each with the QR its screen is showing right now. A resident in
 * a real building scans the physical screen; here the visitor taps the container, or opens its
 * screen on another device and scans it with the phone.
 */
export function DemoContainers({ onPick, disabled }: { onPick: (qr: string) => void; disabled: boolean }) {
    const { data: containers, isError } = useQuery({
        queryKey: ["demo-containers"],
        queryFn: api.demo.containers,
        refetchInterval: 3_000,
    });

    return (
        <Card className="shadow-sm border-0 rounded-xl bg-white">
            <CardHeader>
                <CardTitle className="text-xl text-eco-forest flex items-center">
                    <MonitorSmartphone className="h-5 w-5 mr-2 text-eco-emerald" />
                    Contenedores de la demo
                </CardTitle>
                <CardDescription className="text-eco-forest/70">
                    Simulados con todos sus sensores: báscula, sensor de llenado y detector de metal. Toca uno para usarlo,
                    o abre su pantalla en otro dispositivo y escanéala con tu celular.
                </CardDescription>
            </CardHeader>
            <CardContent>
                {isError && <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">No pudimos cargar los contenedores.</p>}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {(containers ?? []).map((c) => (
                        <div key={c.id} className="rounded-xl border border-eco-forest/10 p-4 flex flex-col gap-3 hover:shadow-md transition-shadow">
                            <div className="flex items-start justify-between gap-2">
                                <div>
                                    <p className="font-semibold text-eco-forest flex items-center">
                                        <Recycle className={`h-5 w-5 mr-2 ${familyOf(c.accepted_materials).icon}`} />
                                        {c.name}
                                    </p>
                                    <p className="text-xs text-eco-forest/60 mt-1">
                                        {c.accepted_materials.map((m) => MATERIALS[m] ?? m).join(" · ")}
                                    </p>
                                </div>
                                <StatusPill online={c.online} busy={c.busy} />
                            </div>
                            <div className="flex justify-center">
                                {c.qr ? (
                                    <ContainerQr value={c.qr} size={148} />
                                ) : (
                                    <div className="w-[148px] h-[148px] rounded-lg bg-eco-forest/5 flex items-center justify-center text-xs text-eco-forest/60 text-center p-4">
                                        {c.online ? "Generando código…" : "Sin conexión"}
                                    </div>
                                )}
                            </div>
                            <div className="flex gap-2">
                                <Button
                                    className="flex-1 bg-eco-emerald text-white hover:bg-eco-emerald/90"
                                    disabled={disabled || !c.qr || c.busy}
                                    onClick={() => c.qr && onPick(c.qr)}
                                >
                                    Usar este contenedor
                                </Button>
                                <Button asChild variant="outline" size="icon" className="text-eco-forest hover:bg-eco-forest/10" title="Abrir la pantalla del contenedor">
                                    <Link to={`/container/${c.id}`} target="_blank" aria-label={`Abrir la pantalla de ${c.name}`}>
                                        <ExternalLink className="h-4 w-4" />
                                    </Link>
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}
