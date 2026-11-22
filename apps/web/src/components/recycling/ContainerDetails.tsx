import { MapPin, Recycle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type ContainerInfo, MATERIALS, familyOf } from "@zyrcle/client";
import { StatusPill } from "./StatusPill";

export function ContainerDetails({ container }: { container: ContainerInfo }) {
    return (
        <Card className="shadow-sm border-eco-emerald/20 rounded-xl bg-gradient-to-br from-eco-lime/10 to-eco-emerald/10 animate-in fade-in duration-300">
            <CardHeader>
                <CardTitle className="text-xl text-eco-forest flex items-center">
                    <Recycle className={`h-6 w-6 mr-2 ${familyOf(container.accepted_materials).icon}`} />
                    Contenedor conectado
                </CardTitle>
                <CardDescription className="text-eco-forest/70">El contenedor que estás usando</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex items-center justify-between gap-4">
                    <span className="text-sm font-medium text-eco-forest/80">Nombre</span>
                    <span className="text-sm font-semibold text-eco-forest text-right">{container.name}</span>
                </div>
                {container.site_name && (
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-sm font-medium text-eco-forest/80">Ubicación</span>
                        <span className="text-sm font-semibold text-eco-forest flex items-center text-right">
                            <MapPin className="h-4 w-4 mr-1 text-eco-emerald shrink-0" />
                            {container.host_name ? `${container.site_name} · ${container.host_name}` : container.site_name}
                        </span>
                    </div>
                )}
                <div className="flex items-center justify-between gap-4">
                    <span className="text-sm font-medium text-eco-forest/80">Recibe</span>
                    <span className="text-sm font-semibold text-eco-forest text-right">
                        {container.accepted_materials.map((m) => MATERIALS[m] ?? m).join(" · ")}
                    </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                    <span className="text-sm font-medium text-eco-forest/80">Estado</span>
                    <StatusPill online={container.online} busy={container.busy} />
                </div>
                {!container.online && (
                    <div className="bg-amber-50 p-3 rounded-lg text-sm text-amber-800">
                        Este contenedor está sin conexión y no puede abrirse ahora.
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
