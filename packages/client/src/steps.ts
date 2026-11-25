/** What each step of a deposit says to the participant, in Spanish (docs/adr/0041). The web app
 * and the mobile app show the same words. */
import type { DepositStep, HistoryEntry } from "./api";
import { grams, pesos } from "./format";

export interface StepLine {
  title: string;
  detail: string | null;
}

export function stepLine(step: DepositStep, entry: HistoryEntry): StepLine {
  const { status, note } = step;
  switch (step.key) {
    case "deposited":
      return {
        title: "Depositado",
        detail: entry.deposited_g !== null ? `${grams(entry.deposited_g)} en ${entry.container_name}` : entry.container_name,
      };
    case "verified":
      if (status === "failed") return { title: "No aprobado", detail: note ? `Motivo: ${note}` : null };
      if (status === "pending") return { title: "En revisión", detail: "Una persona revisa tu depósito." };
      return { title: note === "approved_after_review" ? "Aprobado tras revisión" : "Verificado", detail: null };
    case "advance":
      if (status === "skipped") return { title: "Sin anticipo", detail: "Te pagamos tu parte cuando se venda." };
      if (status === "failed") return { title: "El anticipo falló", detail: "El equipo de Zyrcle lo revisa." };
      if (status === "done") return { title: "Anticipo pagado", detail: step.amount_cop !== null ? pesos(step.amount_cop) : null };
      return {
        title: "Anticipo en camino",
        detail: note === "deferred" ? "La tesorería espera fondos; te llega apenas los tenga." : step.amount_cop !== null ? pesos(step.amount_cop) : null,
      };
    case "collected":
      return status === "done"
        ? { title: "Recogido", detail: "Salió del contenedor en una bolsa sellada." }
        : { title: "Esperando la recolección", detail: null };
    case "sold":
      return status === "done"
        ? { title: "Vendido", detail: note ? `A ${note}` : null }
        : { title: "Esperando la venta", detail: null };
    case "paid":
      if (status === "done") {
        const share = step.share_cop !== null ? pesos(step.share_cop) : null;
        if (note === "covered_by_advance")
          return { title: "Liquidado", detail: share ? `Tu parte fue ${share}; el anticipo ya la cubría.` : null };
        return {
          title: "Pagado",
          detail: step.amount_cop !== null ? `${pesos(step.amount_cop)} más${share ? `, de una parte de ${share}` : ""}` : null,
        };
      }
      return { title: "Esperando el pago del comprador", detail: null };
  }
}

/** The step that tells where the deposit is now: the last one done, or the failed one. */
export function currentStep(steps: DepositStep[]): DepositStep | null {
  const failed = steps.find((s) => s.status === "failed");
  if (failed) return failed;
  const done = steps.filter((s) => s.status === "done");
  return done.length ? done[done.length - 1] : null;
}
