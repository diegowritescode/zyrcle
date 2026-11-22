import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { cn } from "@/lib/utils";

/** A container's QR, drawn as its screen would show it. */
export function ContainerQr({ value, size = 176, className }: { value: string; size?: number; className?: string }) {
    const [src, setSrc] = useState("");
    useEffect(() => {
        QRCode.toDataURL(value, { margin: 1, width: size, color: { dark: "#1E4D22", light: "#ffffff" } }).then(setSrc, () => setSrc(""));
    }, [value, size]);
    return src ? (
        <img src={src} width={size} height={size} alt={`QR del contenedor: ${value}`} className={cn("rounded-lg", className)} />
    ) : (
        <div style={{ width: size, height: size }} className={cn("rounded-lg bg-eco-forest/5 animate-pulse", className)} />
    );
}
