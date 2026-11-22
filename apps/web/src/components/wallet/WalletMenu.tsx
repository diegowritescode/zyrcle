import { Check, Copy, KeyRound, Plus, RefreshCw, Wallet } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { pesos, shortHex } from "@zyrcle/client";
import { useWallet } from "@/wallet/context";

/** The hackathon's wallet button, now backed by the embedded wallet or the visitor's own. */
export function WalletMenu({ compact = false }: { compact?: boolean }) {
    const wallet = useWallet();
    const [copied, setCopied] = useState(false);

    const copy = async () => {
        try {
            await navigator.clipboard.writeText(wallet.account);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            /* clipboard blocked */
        }
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    size={compact ? "sm" : "default"}
                    className={cn(
                        "flex items-center gap-2 bg-eco-emerald text-white hover:bg-eco-emerald/90 transition-transform",
                        compact ? "px-3" : "pl-2 pr-3 hover:scale-105",
                    )}
                    aria-label="Tu wallet"
                >
                    <Wallet className="h-4 w-4" />
                    {shortHex(wallet.address)}
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72 bg-white rounded-xl shadow-sm border-eco-emerald/20">
                <DropdownMenuLabel className="text-eco-forest">
                    <span className="block text-xs font-normal text-eco-forest/60">
                        {wallet.kind === "embedded" ? "Wallet de la demo (en este navegador)" : "Tu wallet (MetaMask o Core)"}
                    </span>
                    <span className="block text-2xl font-semibold text-eco-emerald mt-1">
                        {wallet.balance === null ? "—" : pesos(wallet.balance, 0)}
                    </span>
                    <span className="block text-xs font-normal text-eco-forest/60">en ZYR · 1 ZYR = 1 peso · testnet</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={(e) => { e.preventDefault(); copy(); }} className="text-eco-forest">
                    {copied ? <Check className="h-4 w-4 mr-2 text-eco-emerald" /> : <Copy className="h-4 w-4 mr-2" />}
                    <code className="text-xs" title="Tu cuenta: aquí llegan tus ZYR">{shortHex(wallet.account)}</code>
                    <span className="ml-auto text-xs text-eco-forest/60">{copied ? "Copiada" : "Copiar"}</span>
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => wallet.refreshBalance()} className="text-eco-forest">
                    <RefreshCw className="h-4 w-4 mr-2" /> Actualizar saldo
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {wallet.kind === "embedded" ? (
                    <>
                        <DropdownMenuItem onSelect={() => wallet.connectInjected()} className="text-eco-forest">
                            <Wallet className="h-4 w-4 mr-2" /> Usar MetaMask o Core
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => wallet.newEmbedded()} className="text-eco-forest">
                            <KeyRound className="h-4 w-4 mr-2" /> Crear otra wallet de prueba
                        </DropdownMenuItem>
                    </>
                ) : (
                    <>
                        <DropdownMenuItem onSelect={() => wallet.addChain()} className="text-eco-forest">
                            <Plus className="h-4 w-4 mr-2" /> Agregar ZyrcleChain a la wallet
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => wallet.switchToEmbedded()} className="text-eco-forest">
                            <KeyRound className="h-4 w-4 mr-2" /> Volver a la wallet de la demo
                        </DropdownMenuItem>
                    </>
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
