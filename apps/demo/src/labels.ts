export const MATERIALS: Record<string, string> = {
  pet: "PET",
  hdpe: "HDPE",
  metal: "Latas",
  glass: "Vidrio",
  paper: "Papel",
  cardboard: "Cartón",
};

export const ITEMS: Record<string, string> = {
  pet_bottle: "Botella PET",
  hdpe_jug: "Galón HDPE",
  aluminum_can: "Lata de aluminio",
  glass_bottle: "Botella de vidrio",
  cardboard_box: "Caja de cartón",
  paper_stack: "Papel",
  stone: "Piedra (trampa)",
  full_water_bottle: "Botella llena de agua (trampa)",
};

export const STATES: Record<string, string> = {
  authorized: "Abriendo la tapa…",
  open: "Tapa abierta",
  depositing: "Recibiendo material",
  closing: "Cerrando y pesando…",
  verified: "Verificado",
  review: "En revisión",
  approved: "Aprobado",
  rejected: "Rechazado",
  empty: "No se depositó nada",
  expired: "Expiró",
  failed: "Falló",
};

export const FINAL = new Set(["verified", "review", "approved", "rejected", "empty", "expired", "failed"]);

export const pesos = (n: number) =>
  n.toLocaleString("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 2 });
