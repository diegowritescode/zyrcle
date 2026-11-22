import { cn } from "@/lib/utils";

/** The hackathon's Active / Maintenance pill, for a container's live status. */
export function StatusPill({ online, busy }: { online: boolean; busy: boolean }) {
    const [label, style] = !online
        ? ["Sin conexión", "bg-gray-100 text-gray-700"]
        : busy
          ? ["En uso", "bg-amber-100 text-amber-800"]
          : ["Disponible", "bg-green-100 text-green-800"];
    return <span className={cn("px-3 py-1 rounded-full text-xs font-semibold whitespace-nowrap", style)}>{label}</span>;
}
