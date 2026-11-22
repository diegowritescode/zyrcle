/** Display helpers. ZYR is shown as pesos: 1 ZYR = 1 COP. */
export const pesos = (n: number, digits = 0) =>
  n.toLocaleString("es-CO", {
    style: "currency",
    currency: "COP",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

/** Kilos with two decimals below 10 kg (a demo deposit weighs grams) and one above. */
export const kg = (n: number, digits = Math.abs(n) < 10 ? 2 : 1) =>
  `${n.toLocaleString("es-CO", { minimumFractionDigits: digits, maximumFractionDigits: digits })} kg`;

export const grams = (g: number) => (g >= 1000 ? kg(g / 1000, 2) : `${g} g`);

export const shortHex = (hex: string) => `${hex.slice(0, 6)}…${hex.slice(-4)}`;

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });

export const shortDay = (isoDay: string) =>
  new Date(`${isoDay}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "short" });

/** An hour of the day as Colombians say it: 7 → "7:00 a. m.", 12 → "12:00 m.", 15 → "3:00 p. m." */
export const hourLabel = (h: number) => {
  const h24 = ((h % 24) + 24) % 24;
  if (h24 === 12) return "12:00 m.";
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${h12}:00 ${h24 < 12 ? "a. m." : "p. m."}`;
};

/** "7:00 a. m. – 8:00 a. m." for the slot that starts at hour `h`. */
export const slotLabel = (h: number) => `${hourLabel(h)} – ${hourLabel(h + 1)}`;

const WEEKDAYS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** "Hoy", "Mañana" or "jue 26 nov" for a YYYY-MM-DD day, relative to `today` (YYYY-MM-DD). Built
 * by hand: Intl's short dates differ between JavaScript engines (Hermes, V8). */
export const dayLabel = (isoDay: string, today: string) => {
  const [y, m, d] = isoDay.split("-").map(Number);
  const [ty, tm, td] = today.split("-").map(Number);
  const diff = Math.round((Date.UTC(y, m - 1, d) - Date.UTC(ty, tm - 1, td)) / 86_400_000);
  if (diff === 0) return "Hoy";
  if (diff === 1) return "Mañana";
  return `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${d} ${MONTHS[m - 1]}`;
};

/** A date on this device's calendar as YYYY-MM-DD (today by default). */
export const localDay = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
