import { toast } from "sonner";
import { OperatorApiError } from "./api";

/** Show an operator action's failure as a toast and keep the page usable. */
export function failed(e: unknown) {
    toast.error(e instanceof OperatorApiError || e instanceof Error ? e.message : String(e));
}

/** Grams as the console shows them: with a sign when it is a difference. */
export const signedGrams = (g: number) => `${g > 0 ? "+" : ""}${g.toLocaleString("es-CO")} g`;
