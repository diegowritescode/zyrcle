import {
  CREDITED,
  MATERIALS,
  PAYOUT_STATUS,
  STATES,
  currentStep,
  dateTime,
  familyOf,
  grams,
  pesos,
  stepLine,
  type DepositStep,
  type HistoryEntry,
} from "@zyrcle/client";
import { Check, ChevronDown, Circle, Minus, Recycle, X } from "lucide-react-native";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, familyColor, radius, space } from "@/ui/theme";

/** One deposit in the resident's history: material, weight, container, date, its payment (the
 * advance, plus what it got when its bag was sold) and, on tap, its steps up to the settlement
 * (docs/adr/0041). */
export function DepositRow({ entry }: { entry: HistoryEntry }) {
  const [open, setOpen] = useState(false);
  const family = familyOf([entry.declared_material]).key;
  const steps = entry.steps ?? [];
  const now = currentStep(steps);
  const material = MATERIALS[entry.declared_material] ?? entry.declared_material;

  const row = (
    <View style={styles.row}>
      <Recycle color={familyColor[family]} size={22} />
      <View style={{ flex: 1 }}>
        <Text style={styles.title} numberOfLines={1}>
          {material}
          {entry.deposited_g !== null ? ` · ${grams(entry.deposited_g)}` : ""}
        </Text>
        <Text style={styles.sub} numberOfLines={1}>
          {entry.container_name} · {dateTime(entry.created_at)}
        </Text>
        {now && <Text style={styles.where}>{stepLine(now, entry).title}</Text>}
      </View>
      <View style={{ alignItems: "flex-end" }}>
        {entry.payout ? (
          <>
            <Text style={styles.amount}>
              {pesos((entry.payout.status === "confirmed" ? entry.payout.amount_cop : 0) + (entry.settled_cop ?? 0))}
            </Text>
            <Text style={styles.sub}>
              {entry.settled_cop ? "Anticipo + venta" : (PAYOUT_STATUS[entry.payout.status] ?? entry.payout.status)}
            </Text>
          </>
        ) : (
          <Text style={[styles.sub, CREDITED.has(entry.state) && { color: colors.emerald, fontWeight: "600" }]}>
            {STATES[entry.state] ?? entry.state}
          </Text>
        )}
      </View>
      {steps.length > 0 && (
        <ChevronDown color={colors.muted} size={18} style={open ? { transform: [{ rotate: "180deg" }] } : undefined} />
      )}
    </View>
  );

  if (steps.length === 0) return row;
  return (
    <View>
      <Pressable
        onPress={() => setOpen((o) => !o)}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={`Recorrido de ${material} en ${entry.container_name}`}
      >
        {row}
      </Pressable>
      {open && <Steps entry={entry} steps={steps} />}
    </View>
  );
}

const MARK: Record<DepositStep["status"], { Icon: typeof Check; bg: string; fg: string }> = {
  done: { Icon: Check, bg: colors.emerald, fg: colors.white },
  pending: { Icon: Circle, bg: colors.white, fg: colors.muted },
  failed: { Icon: X, bg: colors.danger, fg: colors.white },
  skipped: { Icon: Minus, bg: colors.tint, fg: colors.muted },
};

function Steps({ entry, steps }: { entry: HistoryEntry; steps: DepositStep[] }) {
  return (
    <View style={styles.steps} accessibilityLabel="Recorrido del depósito">
      {steps.map((step, i) => {
        const { title, detail } = stepLine(step, entry);
        const { Icon, bg, fg } = MARK[step.status];
        const quiet = step.status === "pending" || step.status === "skipped";
        return (
          <View key={step.key} style={{ flexDirection: "row", gap: space(3) }}>
            <View style={{ alignItems: "center" }}>
              <View style={[styles.mark, { backgroundColor: bg }, step.status === "pending" && styles.markPending]}>
                <Icon color={fg} size={13} />
              </View>
              {i < steps.length - 1 && <View style={styles.line} />}
            </View>
            <View style={{ flex: 1, paddingBottom: space(3) }}>
              <Text style={[styles.stepTitle, quiet && { color: colors.muted }]}>{title}</Text>
              {detail && <Text style={styles.sub}>{detail}</Text>}
              {step.at && <Text style={styles.sub}>{dateTime(step.at)}</Text>}
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(3), paddingVertical: space(3) },
  title: { fontSize: 15, fontWeight: "600", color: colors.forestDark },
  sub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  where: { fontSize: 12, color: colors.emeraldDark, fontWeight: "600", marginTop: 2 },
  amount: { fontSize: 15, fontWeight: "700", color: colors.emerald },
  steps: { paddingLeft: space(1), paddingBottom: space(2) },
  mark: { width: 22, height: 22, borderRadius: radius.full, alignItems: "center", justifyContent: "center" },
  markPending: { borderWidth: 1, borderColor: colors.border },
  line: { width: 1, flex: 1, minHeight: 12, backgroundColor: colors.border },
  stepTitle: { fontSize: 14, fontWeight: "600", color: colors.forestDark },
});
