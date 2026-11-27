/** Small building blocks in the hackathon's style: white rounded cards, emerald buttons, pills. */
import { LinearGradient } from "expo-linear-gradient";
import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  type PressableProps,
  type StyleProp,
  type TextProps,
  type ViewStyle,
} from "react-native";
import { colors, gradients, radius, space } from "./theme";

export function Title({ style, ...props }: TextProps) {
  return <Text {...props} style={[styles.title, style]} />;
}

export function Heading({ style, ...props }: TextProps) {
  return <Text {...props} style={[styles.heading, style]} />;
}

export function Body({ style, ...props }: TextProps) {
  return <Text {...props} style={[styles.body, style]} />;
}

export function Muted({ style, ...props }: TextProps) {
  return <Text {...props} style={[styles.muted, style]} />;
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function GradientCard({
  children,
  tone = "emerald",
  style,
}: {
  children: ReactNode;
  tone?: keyof typeof gradients;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <LinearGradient colors={gradients[tone]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={[styles.gradient, style]}>
      {children}
    </LinearGradient>
  );
}

type ButtonProps = Omit<PressableProps, "children" | "style"> & {
  title: string;
  icon?: ReactNode;
  variant?: "primary" | "outline";
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({ title, icon, variant = "primary", loading, disabled, style, ...props }: ButtonProps) {
  const primary = variant === "primary";
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        primary ? styles.buttonPrimary : styles.buttonOutline,
        (disabled || loading) && styles.disabled,
        pressed && styles.pressed,
        style,
      ]}
      {...props}
    >
      {loading ? <ActivityIndicator color={primary ? colors.white : colors.emerald} /> : icon}
      <Text style={[styles.buttonText, { color: primary ? colors.white : colors.forest }]}>{title}</Text>
    </Pressable>
  );
}

const PILL = {
  ok: { bg: "#DCFCE7", fg: "#166534" },
  busy: { bg: "#FEF3C7", fg: "#92400E" },
  off: { bg: "#F3F4F6", fg: "#374151" },
  info: { bg: "rgba(132,204,22,0.20)", fg: colors.forestDark },
} as const;

export function Pill({ label, tone = "ok" }: { label: string; tone?: keyof typeof PILL }) {
  return (
    <View style={[styles.pill, { backgroundColor: PILL[tone].bg }]}>
      <Text style={[styles.pillText, { color: PILL[tone].fg }]}>{label}</Text>
    </View>
  );
}

/** One choice among a few, such as a day or a period; the selected one is filled. */
export function Chip({ label, hint, selected, onPress }: { label: string; hint?: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && { color: colors.white }]}>{label}</Text>
      {hint && <Text style={[styles.chipHint, selected && { color: "rgba(255,255,255,0.85)" }]}>{hint}</Text>}
    </Pressable>
  );
}

export function Notice({ text, tone = "danger" }: { text: string; tone?: "danger" | "warn" | "info" }) {
  const palette =
    tone === "danger"
      ? { bg: colors.dangerTint, fg: colors.danger }
      : tone === "warn"
        ? { bg: colors.warnTint, fg: colors.warn }
        : { bg: colors.tint, fg: colors.textSoft };
  return (
    <View accessibilityRole="alert" style={[styles.notice, { backgroundColor: palette.bg }]}>
      <Text style={{ color: palette.fg, fontSize: 14, lineHeight: 20 }}>{text}</Text>
    </View>
  );
}

/** The round lime-to-emerald icon badge of the landing's feature cards. */
export function IconBadge({ children, size = 48 }: { children: ReactNode; size?: number }) {
  return (
    <LinearGradient
      colors={[colors.lime, colors.emerald]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{ width: size, height: size, borderRadius: size / 2, alignItems: "center", justifyContent: "center" }}
    >
      {children}
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.white,
    borderRadius: radius.md,
    paddingHorizontal: space(3),
    paddingVertical: space(2),
    minHeight: 44,
    justifyContent: "center",
  },
  chipSelected: { backgroundColor: colors.emerald, borderColor: colors.emerald },
  chipText: { fontSize: 14, fontWeight: "600", color: colors.forestDark },
  chipHint: { fontSize: 11, color: colors.muted, marginTop: 1 },
  title: { fontSize: 28, fontWeight: "700", color: colors.forestDark, letterSpacing: -0.3 },
  heading: { fontSize: 18, fontWeight: "600", color: colors.forest },
  body: { fontSize: 15, lineHeight: 22, color: colors.textSoft },
  muted: { fontSize: 13, lineHeight: 18, color: colors.muted },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: space(5),
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  gradient: { borderRadius: radius.lg, padding: space(5) },
  button: {
    minHeight: 50,
    borderRadius: radius.md,
    paddingHorizontal: space(5),
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space(2),
  },
  buttonPrimary: { backgroundColor: colors.emerald },
  buttonOutline: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border },
  buttonText: { fontSize: 16, fontWeight: "600" },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.85, transform: [{ scale: 0.98 }] },
  pill: { paddingHorizontal: space(3), paddingVertical: space(1), borderRadius: radius.full, alignSelf: "flex-start" },
  pillText: { fontSize: 12, fontWeight: "600" },
  notice: { borderRadius: radius.md, padding: space(3) },
});
