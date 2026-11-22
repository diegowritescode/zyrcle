/**
 * The web app's eco palette (apps/web/tailwind.config.ts), so the app and the site look like one
 * product. Translucent values mirror Tailwind's `/opacity` classes on a white background.
 */
export const colors = {
  forest: "#2C6E31",
  forestLight: "#4A8C4F",
  forestDark: "#1E4D22",
  lime: "#84CC16",
  limeLight: "#A3E635",
  emerald: "#10B981",
  emeraldLight: "#34D399",
  emeraldDark: "#059669",

  background: "#F9FAFB", // gray-50, the page background of the dashboards
  card: "#FFFFFF",
  border: "rgba(44,110,49,0.10)", // eco-forest/10
  text: "#1E4D22", // eco-forest-dark
  textSoft: "rgba(44,110,49,0.80)",
  muted: "rgba(44,110,49,0.65)",
  tint: "rgba(44,110,49,0.05)", // eco-forest/5
  emeraldTint: "rgba(16,185,129,0.10)",

  danger: "#DC2626",
  dangerTint: "#FEF2F2",
  warn: "#92400E",
  warnTint: "#FFFBEB",
  white: "#FFFFFF",
} as const;

/** Card gradients of the site dashboard. */
export const gradients = {
  emerald: ["rgba(16,185,129,0.85)", "rgba(44,110,49,0.85)"],
  lime: ["rgba(132,204,22,0.85)", "rgba(16,185,129,0.85)"],
  soft: ["rgba(132,204,22,0.10)", "rgba(16,185,129,0.10)"],
} as const;

/** Material family colors, as in the web's container cards. */
export const familyColor: Record<string, string> = {
  plastic: "#3B82F6",
  paper: "#22C55E",
  glass: "#14B8A6",
  metal: "#6B7280",
};

export const radius = { sm: 6, md: 10, lg: 14, xl: 18, full: 999 } as const;
export const space = (n: number) => n * 4;
