import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** Consent to the data-processing policy in force (Ley 1581 de 2012, docs/adr/0028). */
export function PrivacyBanner({ token }: { token: string | null }) {
    const queryClient = useQueryClient();
    const me = useQuery({ queryKey: ["me", token], queryFn: () => api.me(token!), enabled: token !== null });
    const [busy, setBusy] = useState(false);
    if (!me.data || me.data.privacy_version === me.data.privacy_current) return null;
    const accept = async () => {
        setBusy(true);
        try {
            await api.acceptPrivacy(token!, me.data!.privacy_current);
            await queryClient.invalidateQueries({ queryKey: ["me"] });
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="mb-6 rounded-xl border border-eco-emerald/40 bg-white p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-eco-forest/80">
                Usamos la dirección de tu cuenta y tus depósitos solo para pagarte y avisarte; los pagos quedan en la cadena, sin tu nombre.{" "}
                <Link to="/privacidad" className="underline">Política de tratamiento de datos</Link>.
            </p>
            <Button size="sm" disabled={busy} onClick={accept} className="self-start sm:self-auto">
                <ShieldCheck className="h-4 w-4 mr-1" /> Acepto
            </Button>
        </div>
    );
}
