import { Check, Circle, Minus, X } from "lucide-react";
import { dateTime, stepLine, type DepositStep, type HistoryEntry } from "@zyrcle/client";

const ICON: Record<DepositStep["status"], { icon: typeof Check; className: string }> = {
    done: { icon: Check, className: "bg-eco-emerald text-white" },
    pending: { icon: Circle, className: "bg-white text-eco-forest/30 border border-eco-forest/20" },
    failed: { icon: X, className: "bg-red-600 text-white" },
    skipped: { icon: Minus, className: "bg-gray-100 text-gray-400" },
};

/** A deposit's way from the lid to the settlement (docs/adr/0041). */
export function DepositSteps({ entry }: { entry: HistoryEntry }) {
    const steps = entry.steps ?? [];
    return (
        <ol className="mt-3 ml-1 space-y-0" aria-label="Recorrido del depósito">
            {steps.map((step, i) => {
                const { title, detail } = stepLine(step, entry);
                const { icon: Icon, className } = ICON[step.status];
                const day = step.key === "sold" && step.at ? new Date(step.at).toLocaleDateString("es-CO", { dateStyle: "medium" }) : step.at ? dateTime(step.at) : null;
                return (
                    <li key={step.key} className="flex gap-3">
                        <div className="flex flex-col items-center">
                            <span className={`flex h-6 w-6 items-center justify-center rounded-full ${className}`}>
                                <Icon className="h-3.5 w-3.5" />
                            </span>
                            {i < steps.length - 1 && <span className="w-px flex-1 min-h-4 bg-eco-forest/15" />}
                        </div>
                        <div className={`pb-3 ${step.status === "pending" || step.status === "skipped" ? "text-eco-forest/50" : "text-eco-forest"}`}>
                            <p className="text-sm font-medium">{title}</p>
                            {detail && <p className="text-xs">{detail}</p>}
                            {day && <p className="text-xs text-eco-forest/50">{day}</p>}
                        </div>
                    </li>
                );
            })}
        </ol>
    );
}
