/** Spanish labels for the API's identifiers. */
export const MATERIALS: Record<string, string> = {
  pet: "PET",
  hdpe: "HDPE",
  metal: "Latas",
  glass: "Vidrio",
  paper: "Papel",
  cardboard: "Cartón",
};

/** Material families: the four series of the hackathon dashboard (plastic, paper, glass, metal). */
export type Family = "plastic" | "paper" | "glass" | "metal";

export const FAMILY_OF: Record<string, Family> = {
  pet: "plastic",
  hdpe: "plastic",
  paper: "paper",
  cardboard: "paper",
  glass: "glass",
  metal: "metal",
};

export const FAMILIES: { key: Family; label: string; color: string; icon: string; track: string }[] = [
  { key: "plastic", label: "Plástico", color: "#10B981", icon: "text-blue-500", track: "bg-blue-100" },
  { key: "paper", label: "Papel y cartón", color: "#84CC16", icon: "text-green-500", track: "bg-green-100" },
  { key: "glass", label: "Vidrio", color: "#2C6E31", icon: "text-teal-500", track: "bg-teal-100" },
  { key: "metal", label: "Metal", color: "#4A8C4F", icon: "text-gray-500", track: "bg-gray-100" },
];

export const familyOf = (materials: string[]) =>
  FAMILIES.find((f) => f.key === FAMILY_OF[materials[0]]) ?? FAMILIES[0];

/** Items the demo's simulated container can receive (device/simulator CATALOG). */
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

export const ACTIVE = new Set(["authorized", "open", "depositing", "closing"]);
export const LID_OPEN = new Set(["open", "depositing"]);
export const CREDITED = new Set(["verified", "approved"]);

export const PAYOUT_STATUS: Record<string, string> = {
  pending: "en cola",
  submitting: "enviando a la cadena",
  confirmed: "pagado en la cadena",
  deferred: "aplazado",
  failed: "falló",
};
