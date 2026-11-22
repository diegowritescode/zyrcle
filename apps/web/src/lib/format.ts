/** Display helpers. ZYR is shown as pesos: 1 ZYR = 1 COP. */
export const pesos = (n: number, digits = 0) =>
  n.toLocaleString("es-CO", {
    style: "currency",
    currency: "COP",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

export const kg = (n: number, digits = 1) =>
  `${n.toLocaleString("es-CO", { minimumFractionDigits: digits, maximumFractionDigits: digits })} kg`;

export const grams = (g: number) => (g >= 1000 ? kg(g / 1000, 2) : `${g} g`);

export const shortHex = (hex: string) => `${hex.slice(0, 6)}…${hex.slice(-4)}`;

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });

export const shortDay = (isoDay: string) =>
  new Date(`${isoDay}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "short" });
