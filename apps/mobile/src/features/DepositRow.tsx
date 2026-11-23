import { CREDITED, MATERIALS, PAYOUT_STATUS, STATES, dateTime, familyOf, grams, pesos, type HistoryEntry } from "@zyrcle/client";
import { Recycle } from "lucide-react-native";
import { StyleSheet, Text, View } from "react-native";
import { colors, familyColor, space } from "@/ui/theme";

/** One deposit in the resident's history: material, weight, container, date and its payment (the
 * advance, plus what it got when its bag was sold). */
export function DepositRow({ entry }: { entry: HistoryEntry }) {
  const family = familyOf([entry.declared_material]).key;
  return (
    <View style={styles.row}>
      <Recycle color={familyColor[family]} size={22} />
      <View style={{ flex: 1 }}>
        <Text style={styles.title} numberOfLines={1}>
          {MATERIALS[entry.declared_material] ?? entry.declared_material}
          {entry.deposited_g !== null ? ` · ${grams(entry.deposited_g)}` : ""}
        </Text>
        <Text style={styles.sub} numberOfLines={1}>
          {entry.container_name} · {dateTime(entry.created_at)}
        </Text>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        {entry.payout ? (
          <>
            <Text style={styles.amount}>{pesos(entry.payout.amount_cop + (entry.settled_cop ?? 0))}</Text>
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
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(3), paddingVertical: space(3) },
  title: { fontSize: 15, fontWeight: "600", color: colors.forestDark },
  sub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  amount: { fontSize: 15, fontWeight: "700", color: colors.emerald },
});
