import { useCallback, useEffect, useRef, useState } from "react";
import { Check, CircleDollarSign, Edit, Loader2, QrCode, Recycle } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Tooltip as UITooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useIsMobile } from "@/hooks/use-mobile";
import { useDepositSession } from "@/hooks/useDepositSession";
import { api, ApiError, type ContainerInfo } from "@/lib/api";
import { pesos } from "@/lib/format";
import { ACTIVE, MATERIALS } from "@/lib/labels";
import { containerQr, parseContainerQr, parseManualCode } from "@/lib/qr";
import { cn } from "@/lib/utils";
import { useWallet } from "@/wallet/context";
import { ContainerDetails } from "./ContainerDetails";
import { DemoContainers } from "./DemoContainers";
import { QrScanner } from "./QrScanner";
import { ResultPanel } from "./ResultPanel";
import { SessionPanel } from "./SessionPanel";

function startError(e: unknown): string {
    if (!(e instanceof ApiError)) return "Algo salió mal. Intenta de nuevo.";
    const d = e.message;
    if (e.status === 0) return d;
    if (/invalid or expired/.test(d)) return "El código del QR ya cambió. Escanéalo de nuevo.";
    if (/offline/.test(d)) return "El contenedor está sin conexión.";
    if (/busy/.test(d)) return "Otra persona está usando este contenedor. Espera un momento.";
    if (/does not accept/.test(d)) return "Este contenedor no recibe ese material.";
    if (/could not reach/.test(d)) return "No pudimos comunicarnos con el contenedor. Intenta de nuevo.";
    if (/unknown container/.test(d)) return "Ese contenedor no existe.";
    return d;
}

/**
 * The resident's side of a deposit, in the hackathon's design: scan the container, choose the
 * material, deposit while the scale reads live, tap "Terminé", and see the verdict and the payment.
 */
export function RecyclingAccess() {
    const wallet = useWallet();
    const queryClient = useQueryClient();
    const isMobile = useIsMobile();
    const [mode, setMode] = useState<"idle" | "camera" | "manual">("idle");
    const [manual, setManual] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [scanned, setScanned] = useState<{ qr: string; container: ContainerInfo } | null>(null);
    const [material, setMaterial] = useState<string>("");
    const [busy, setBusy] = useState(false);

    const { token, ensureToken, kind, address, refreshBalance } = wallet;

    const onPaid = useCallback(() => {
        refreshBalance();
        queryClient.invalidateQueries({ queryKey: ["me"] });
    }, [refreshBalance, queryClient]);
    const deposit = useDepositSession(token, onPaid);
    const session = deposit.session;

    // Sign in as soon as the page opens when it is silent (embedded wallet). A browser wallet asks
    // for its signature only when the resident opens a container.
    useEffect(() => {
        if (kind === "embedded") ensureToken().catch(() => setError("No pudimos iniciar sesión con tu wallet."));
    }, [kind, address, ensureToken]);

    // Another wallet means another resident: drop whatever the previous one was doing.
    const lastAddress = useRef(address);
    const { reset } = deposit;
    useEffect(() => {
        if (lastAddress.current === address) return;
        lastAddress.current = address;
        reset();
        setScanned(null);
    }, [address, reset]);

    const run = async (fn: () => Promise<void>) => {
        setError(null);
        setBusy(true);
        try {
            await fn();
        } catch (e) {
            setError(startError(e));
        } finally {
            setBusy(false);
        }
    };

    const handleCode = (raw: string) =>
        run(async () => {
            const parsed = parseContainerQr(raw) ?? parseManualCode(raw);
            if (!parsed) {
                toast.error("Ese no es un código de Zyrcle", { description: "Escanea el QR de la pantalla del contenedor." });
                return;
            }
            const container = await api.container(parsed.containerId);
            setScanned({ qr: containerQr(parsed.containerId, parsed.code), container });
            setMaterial(container.accepted_materials[0]);
            setMode("idle");
            setManual("");
        });

    const open = () =>
        run(async () => {
            if (!scanned) return;
            const t = await ensureToken();
            try {
                await deposit.start(t, scanned.qr, material);
            } catch (e) {
                // A session left open in another tab: pick it up instead of failing.
                if (e instanceof ApiError && /already have an open session/.test(e.message)) {
                    const me = await api.me(t);
                    const active = me.sessions.find((s) => ACTIVE.has(s.state));
                    if (active) return deposit.resume(t, active.id);
                }
                throw e;
            }
        });

    // Drops do not block the page: a resident throws several items in a row.
    const drop = (item: string) => {
        if (!token || !session) return;
        api.demo.drop(token, session.id, item).catch((e) => setError(startError(e)));
    };

    const finish = () =>
        run(async () => {
            if (token && session) await api.finish(token, session.id);
        });

    const again = () => {
        deposit.reset();
        setScanned(null);
        setError(null);
    };

    const container = scanned?.container ?? null;
    const subtitle = session
        ? `${ACTIVE.has(session.state) ? "Estás reciclando" : "Reciclaste"} en ${container?.name ?? session.container_id}`
        : scanned
          ? `Conectado a ${scanned.container.name}`
          : "Escanea o escribe el código del contenedor para empezar";
    const showCamera = mode === "camera" || (mode === "idle" && isMobile && !scanned);

    return (
        <div className="space-y-8 p-4 max-w-4xl mx-auto bg-gradient-to-b from-eco-lime/5 to-eco-emerald/5 rounded-2xl">
            <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-4">
                {/* Encabezado principal */}
                <div className="text-center sm:text-left">
                    <h1 className="text-3xl font-bold text-eco-forest flex items-center justify-center sm:justify-start">
                        <Recycle className="h-8 w-8 mr-2 text-eco-emerald" />
                        Reciclaje inteligente
                    </h1>
                    <p className="text-eco-forest/70 mt-2">{subtitle}</p>
                </div>

                {/* Tarjeta de saldo */}
                <Card className="shadow-sm border-0 rounded-xl bg-white sm:min-w-[220px]">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-eco-forest flex items-center">
                            <CircleDollarSign className="h-4 w-4 mr-2 text-eco-emerald" />
                            Tu saldo
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-xl font-semibold text-eco-emerald">
                            {wallet.balance === null ? "—" : pesos(wallet.balance)}
                        </div>
                        <p className="text-xs text-eco-forest/60">
                            en ZYR · {wallet.signingIn ? "firmando…" : token ? "sesión iniciada con tu firma" : "sin sesión"}
                        </p>
                    </CardContent>
                </Card>
            </div>

            {error && (
                <p role="alert" className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">
                    {error}
                </p>
            )}

            {/* Tarjeta principal */}
            <Card className="shadow-sm border-0 rounded-xl bg-white">
                <CardHeader>
                    <CardTitle className="text-xl text-eco-forest">
                        {session ? (ACTIVE.has(session.state) ? "Deposita y cierra" : "Resultado") : scanned ? "¿Qué vas a reciclar?" : "Accede a un contenedor"}
                    </CardTitle>
                    <CardDescription className="text-eco-forest/70">
                        {session
                            ? ACTIVE.has(session.state)
                                ? "El contenedor pesa en vivo y verifica al cerrar."
                                : "Así quedó tu depósito."
                            : scanned
                              ? "Elige el material y el contenedor abre la tapa."
                              : "Usa la cámara para leer el QR de la pantalla del contenedor, o escribe el código que aparece debajo."}
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6 transition-all duration-300">
                    {session ? (
                        ACTIVE.has(session.state) ? (
                            <SessionPanel
                                session={session}
                                container={container}
                                weight={deposit.weight}
                                busy={busy}
                                onDrop={drop}
                                onFinish={finish}
                            />
                        ) : (
                            <ResultPanel session={session} payout={deposit.payout} onAgain={again} />
                        )
                    ) : scanned ? (
                        <div className="space-y-6 animate-in fade-in duration-300">
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3" role="radiogroup" aria-label="Material">
                                {scanned.container.accepted_materials.map((m) => (
                                    <button
                                        key={m}
                                        role="radio"
                                        aria-checked={material === m}
                                        onClick={() => setMaterial(m)}
                                        className={cn(
                                            "rounded-xl border-2 p-4 text-left transition-colors",
                                            material === m
                                                ? "border-eco-emerald bg-eco-emerald/10 text-eco-forest"
                                                : "border-eco-forest/10 text-eco-forest/80 hover:border-eco-emerald/50",
                                        )}
                                    >
                                        <span className="font-semibold">{MATERIALS[m] ?? m}</span>
                                    </button>
                                ))}
                            </div>
                            <div className="flex gap-4">
                                <Button
                                    onClick={open}
                                    disabled={busy || !material || !scanned.container.online}
                                    className="flex-1 bg-eco-emerald text-white hover:bg-eco-emerald/90 hover:scale-105 transition-transform duration-200"
                                >
                                    {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Recycle className="h-4 w-4 mr-2" />}
                                    Abrir contenedor
                                </Button>
                                <Button variant="outline" onClick={again} className="text-eco-forest hover:bg-eco-forest/10">
                                    Cancelar
                                </Button>
                            </div>
                            <p className="text-xs text-eco-forest/60">
                                El código del QR cambia cada 30 segundos. Si vence antes de abrir, escanéalo de nuevo.
                            </p>
                        </div>
                    ) : showCamera ? (
                        <div className="space-y-4">
                            <div className="relative aspect-square max-w-md mx-auto">
                                <QrScanner onCode={handleCode} onError={(m) => { setError(m); setMode("manual"); }} />
                                <div className="absolute inset-0 border-4 border-eco-emerald/50 rounded-lg pointer-events-none animate-pulse" />
                            </div>
                            <p className="text-center text-sm text-eco-forest/70">Apunta la cámara al QR de la pantalla del contenedor</p>
                            <Button variant="outline" className="w-full text-eco-forest hover:bg-eco-forest/10" onClick={() => setMode("manual")}>
                                <Edit className="h-4 w-4 mr-2" />
                                Escribir el código a mano
                            </Button>
                        </div>
                    ) : mode === "manual" ? (
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                handleCode(manual);
                            }}
                            className="space-y-4"
                        >
                            <Input
                                type="text"
                                placeholder="ctr-0001 7KQ2MX"
                                value={manual}
                                onChange={(e) => setManual(e.target.value)}
                                maxLength={90}
                                autoCapitalize="none"
                                autoCorrect="off"
                                spellCheck={false}
                                aria-label="Código del contenedor"
                                className="text-center text-lg"
                            />
                            <div className="flex space-x-4">
                                <Button type="submit" disabled={busy || !manual.trim()} className="flex-1 bg-eco-emerald text-white hover:bg-eco-emerald/90">
                                    <Check className="h-4 w-4 mr-2" />
                                    Usar código
                                </Button>
                                <Button type="button" variant="outline" className="flex-1 text-eco-forest hover:bg-eco-forest/10" onClick={() => { setError(null); setMode("camera"); }}>
                                    <QrCode className="h-4 w-4 mr-2" />
                                    Escanear QR
                                </Button>
                            </div>
                        </form>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <UITooltip>
                                <TooltipTrigger asChild>
                                    <Button onClick={() => setMode("camera")} className="h-14 bg-eco-emerald text-white hover:bg-eco-emerald/90 hover:scale-105 transition-transform duration-200">
                                        <QrCode className="h-5 w-5 mr-2" />
                                        Escanear QR con la cámara
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>Lee el QR de la pantalla del contenedor</TooltipContent>
                            </UITooltip>
                            <Button variant="outline" onClick={() => setMode("manual")} className="h-14 text-eco-forest hover:bg-eco-forest/10">
                                <Edit className="h-5 w-5 mr-2" />
                                Escribir el código a mano
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Detalles del contenedor conectado */}
            {container && <ContainerDetails container={container} />}

            {!session && !scanned && <DemoContainers onPick={handleCode} disabled={busy} />}
        </div>
    );
}
