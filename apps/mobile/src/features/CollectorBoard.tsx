import { useQuery } from "@tanstack/react-query";
import { ago, grams, monthLabel, pesos, type CollectorContainer } from "@zyrcle/client";
import { StyleSheet, Text, View } from "react-native";
import { api } from "@/lib/api";
import { Card, Heading, Muted, Pill } from "@/ui/kit";
import { colors, radius, space } from "@/ui/theme";

const ALERT_PCT = 80; // the API's default ZYRCLE_FILL_ALERT_PCT (docs/adr/0042)

/** The collector's containers, fullest first, so the round starts where it is needed. */
export function ContainersCard({ containers }: { containers: CollectorContainer[] }) {
  if (containers.length === 0) return null;
  return (
    <Card style={{ gap: space(3) }}>
      <Heading>Qué vaciar primero</Heading>
      <Muted>Del más lleno al más vacío; a igual llenado, el que lleva más tiempo sin vaciarse.</Muted>
      {containers.map((c) => {
        const full = c.fill_pct !== null && c.fill_pct >= ALERT_PCT;
        return (
          <View key={c.id} style={{ gap: space(1) }} accessibilityLabel={`${c.name}, ${c.fill_pct === null ? "llenado desconocido" : `${c.fill_pct} %`}`}>
            <View style={styles.row}>
              <Text style={styles.name} numberOfLines={1}>
                {c.name}
              </Text>
              {full ? <Pill label="Vaciar ya" tone="busy" /> : null}
              <Text style={styles.pct}>{c.fill_pct === null ? "—" : `${c.fill_pct} %`}</Text>
            </View>
            <View style={styles.track}>
              <View style={[styles.fill, { width: `${c.fill_pct ?? 0}%` }, full && { backgroundColor: colors.warn }]} />
            </View>
            <Muted style={styles.meta}>
              {c.site.name} · {c.last_emptied_at ? `vaciado ${ago(c.last_emptied_at)}` : "nunca vaciado"} · {c.deposits_since}{" "}
              {c.deposits_since === 1 ? "depósito" : "depósitos"} desde entonces
            </Muted>
          </View>
        );
      })}
    </Card>
  );
}

/** What the collector's collections paid: per month, and the latest ones one by one. */
export function EarningsCard({ token }: { token: string | null }) {
  const earnings = useQuery({ queryKey: ["collector-earnings", token], queryFn: () => api.earnings(token!), enabled: token !== null, refetchInterval: 60_000 });
  const data = earnings.data;
  if (!data || data.collections.length === 0) return null;
  const recent = data.collections.slice(0, 6);
  return (
    <Card style={{ gap: space(3) }}>
      <Heading>Lo que has ganado</Heading>
      <View style={styles.months}>
        {data.months
          .filter((m) => m.collections > 0)
          .map((m) => (
            <View key={m.month} style={styles.month}>
              <Text style={styles.meta}>{monthLabel(m.month)}</Text>
              <Text style={styles.amount}>{pesos(m.earned_cop)}</Text>
              <Text style={styles.meta}>
                {m.collections} {m.collections === 1 ? "recolección" : "recolecciones"} · {grams(m.grams)}
              </Text>
            </View>
          ))}
      </View>
      {recent.map((c) => (
        <View key={c.id} style={styles.row}>
          <View style={{ flex: 1 }}>
            <Text style={styles.name} numberOfLines={1}>
              {c.container_name}
            </Text>
            <Muted style={styles.meta}>
              {c.closed_at ? ago(c.closed_at) : ""} · {grams(c.grams)}
              {c.pending_g > 0 ? ` · ${grams(c.pending_g)} sin vender` : ""}
            </Muted>
          </View>
          <Text style={styles.amount}>{pesos(c.earned_cop)}</Text>
        </View>
      ))}
      <Muted style={styles.meta}>Te pagamos tu parte cuando el centro de acopio paga la bolsa.</Muted>
    </Card>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(2) },
  name: { flex: 1, fontSize: 14, fontWeight: "600", color: colors.forestDark },
  pct: { fontSize: 14, fontWeight: "700", color: colors.forestDark, minWidth: 44, textAlign: "right" },
  track: { height: 8, borderRadius: radius.full, backgroundColor: colors.tint, overflow: "hidden" },
  fill: { height: "100%", borderRadius: radius.full, backgroundColor: colors.emerald },
  meta: { fontSize: 12, color: colors.muted },
  months: { flexDirection: "row", flexWrap: "wrap", gap: space(2) },
  month: { flexGrow: 1, minWidth: 120, backgroundColor: colors.tint, borderRadius: radius.md, padding: space(2.5) },
  amount: { fontSize: 15, fontWeight: "700", color: colors.emerald },
});
