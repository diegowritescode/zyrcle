import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** A titled block of the console, in the hackathon's card style. */
export function Section({ title, description, actions, children }: { title: string; description?: string; actions?: ReactNode; children: ReactNode }) {
    return (
        <Card className="shadow-sm border-0 rounded-xl bg-white">
            <CardHeader className="bg-eco-forest/5 rounded-t-xl">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                        <CardTitle className="text-lg text-eco-forest">{title}</CardTitle>
                        {description && <CardDescription className="text-eco-forest/70">{description}</CardDescription>}
                    </div>
                    {actions}
                </div>
            </CardHeader>
            <CardContent className="p-4 sm:p-6">{children}</CardContent>
        </Card>
    );
}

export function Loading() {
    return <Loader2 className="h-6 w-6 mx-auto my-8 animate-spin text-eco-emerald" aria-label="Cargando" />;
}

export function Empty({ children }: { children: ReactNode }) {
    return <p className="text-sm text-eco-forest/60 text-center py-6">{children}</p>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
    return (
        <div className="rounded-xl bg-eco-forest/5 p-4">
            <p className="text-xs font-medium text-eco-forest/70">{label}</p>
            <p className="text-2xl font-bold text-eco-forest mt-1">{value}</p>
            {hint && <p className="text-xs text-eco-forest/60 mt-1">{hint}</p>}
        </div>
    );
}
