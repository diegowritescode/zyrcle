import { useState } from "react";
import { KeyRound, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConsole } from "@/console/context";
import { failed } from "@/console/format";

/** Sign in with a code sent to the operator's email (docs/adr/0014). */
export function Login() {
    const { api, signIn } = useConsole();
    const [email, setEmail] = useState("");
    const [code, setCode] = useState("");
    const [sentTo, setSentTo] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const send = async () => {
        setBusy(true);
        try {
            setSentTo((await api.requestCode(email)).sent_to);
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };
    const enter = async () => {
        setBusy(true);
        try {
            signIn((await api.login(email, code)).token);
        } catch (e) {
            failed(e);
        } finally {
            setBusy(false);
        }
    };

    return (
        <Card className="max-w-md mx-auto shadow-sm border-0 rounded-xl bg-white">
            <CardHeader>
                <CardTitle className="text-eco-forest flex items-center gap-2">
                    <KeyRound className="h-5 w-5 text-eco-emerald" />
                    Consola de operación
                </CardTitle>
                <CardDescription>Para operadores de Zyrcle. Te enviamos un código a tu correo.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <form
                    className="space-y-2"
                    onSubmit={(e) => {
                        e.preventDefault();
                        if (email.trim()) send();
                    }}
                >
                    <Label htmlFor="op-email">Correo</Label>
                    <Input id="op-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                    <Button type="submit" variant="outline" className="w-full" disabled={busy || !email.trim()}>
                        <Mail className="h-4 w-4 mr-2" />
                        {sentTo ? "Enviarme otro código" : "Enviarme un código"}
                    </Button>
                </form>
                {sentTo && (
                    <form
                        className="space-y-2"
                        onSubmit={(e) => {
                            e.preventDefault();
                            if (code.trim()) enter();
                        }}
                    >
                        <p className="text-sm text-eco-forest/70">Si {sentTo} es de un operador, le llegó un código de 6 números.</p>
                        <Label htmlFor="op-code">Código</Label>
                        <Input id="op-code" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
                        <Button type="submit" className="w-full" disabled={busy || code.trim().length < 6}>
                            Entrar
                        </Button>
                    </form>
                )}
            </CardContent>
        </Card>
    );
}
