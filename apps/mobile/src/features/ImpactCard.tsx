import { useQuery } from "@tanstack/react-query";
import { MATERIALS, co2e, grams, monthLabel } from "@zyrcle/client";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { api } from "@/lib/api";
import { Card, Heading, Muted } from "@/ui/kit";
import { colors, radius, space } from "@/ui/theme";

/** The participant's own impact (docs/adr/0041): recycled, sold, and the CO2e avoided by what was
 * sold, with the certificates' factors (docs/adr/0027). Tap a month to read its figures. */
export function ImpactCard({ token }: { token: string | null }) {
  const impact = useQuery({ queryKey: ["impact", token], queryFn: () => api.impact(token!), enabled: token !== null, refetchInterval: 60_000 });
  const [picked, setPicked] = useState<number | null>(null);
  const data = impact.data;
  if (!data || data.deposits === 0) return null;
  const top = Math.max(1, ...data.months.map((m) => m.verified_g));
  const shown = data.months[picked ?? data.months.length - 1];

  return (
    <Card style={{ gap: space(3) }}>
      <Heading>Mi impacto</Heading>
      <View style={styles.stats}>
        <Stat label="Verificado" value={grams(data.totals.verified_g)} />
        <Stat label="Vendido" value={grams(data.totals.sold_g)} />
        <Stat label="CO2e evitado" value={co2e(data.totals.co2e_g)} />
      </View>
      <View>
        <Text style={styles.caption}>
          {monthLabel(shown.month)}: {grams(shown.verified_g)} verificados · {grams(shown.sold_g)} vendidos
        </Text>
        <View style={styles.bars}>
          {data.months.map((m, i) => (
            <Pressable
              key={m.month}
              style={styles.slot}
              onPress={() => setPicked(i)}
              accessibilityRole="button"
              accessibilityLabel={`${monthLabel(m.month)}: ${grams(m.verified_g)} verificados, ${grams(m.sold_g)} vendidos`}
            >
              <View
                style={[
                  styles.bar,
                  { height: m.verified_g ? `${Math.max(4, (100 * m.verified_g) / top)}%` : 0 },
                  (picked ?? data.months.length - 1) === i && { backgroundColor: colors.forest },
                ]}
              />
            </Pressable>
          ))}
        </View>
      </View>
      {data.materials.map((m) => (
        <View key={m.material} style={styles.material}>
          <Text style={styles.materialName}>{MATERIALS[m.material] ?? m.material}</Text>
          <Text style={styles.meta}>
            {grams(m.verified_g)} · vendido {grams(m.sold_g)} · {co2e(m.co2e_g)} CO2e
          </Text>
        </View>
      ))}
      <Muted style={{ fontSize: 12 }}>
        El CO2e cuenta solo lo vendido, con los factores de los certificados (EPA WARM v16). Es indicativo, no un crédito de carbono.
      </Muted>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.meta}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  stats: { flexDirection: "row", gap: space(2) },
  stat: { flex: 1, backgroundColor: colors.tint, borderRadius: radius.md, padding: space(2.5) },
  value: { fontSize: 16, fontWeight: "700", color: colors.forestDark, marginTop: 2 },
  caption: { fontSize: 12, color: colors.muted, marginBottom: space(1) },
  bars: { flexDirection: "row", alignItems: "flex-end", gap: 2, height: 72, borderBottomWidth: 1, borderBottomColor: colors.border },
  slot: { flex: 1, height: "100%", justifyContent: "flex-end" },
  bar: { width: "100%", backgroundColor: colors.emerald, borderTopLeftRadius: 4, borderTopRightRadius: 4 },
  material: { flexDirection: "row", justifyContent: "space-between", gap: space(2) },
  materialName: { fontSize: 14, fontWeight: "600", color: colors.forestDark },
  meta: { fontSize: 12, color: colors.muted },
});
