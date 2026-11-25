import { useQuery } from "@tanstack/react-query";
import type { MerchantListing } from "@zyrcle/client";
import { Clock, MapPin } from "lucide-react-native";
import { StyleSheet, Text, View } from "react-native";
import { api } from "@/lib/api";
import { Card, Heading, Muted } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, space } from "@/ui/theme";

/** The campus merchants that take ZYR, by institution and campus (docs/adr/0041). */
export default function Spend() {
  const list = useQuery({ queryKey: ["merchants"], queryFn: api.merchants, staleTime: 60_000 });
  const groups = new Map<string, { title: string; items: MerchantListing[] }>();
  for (const m of list.data ?? []) {
    const key = `${m.host.id}/${m.site?.id ?? ""}`;
    if (!groups.has(key)) groups.set(key, { title: m.site ? `${m.host.name} · ${m.site.name}` : m.host.name, items: [] });
    groups.get(key)!.items.push(m);
  }

  return (
    <Screen edges={[]} refreshing={list.isRefetching} onRefresh={() => list.refetch()}>
      <Muted>Estos comercios reciben tus ZYR: 1 ZYR vale 1 peso. Pagas escaneando el QR de su cobro.</Muted>
      {list.isLoading ? (
        <Muted>Cargando…</Muted>
      ) : groups.size === 0 ? (
        <Card>
          <Muted>Todavía no hay comercios en tu campus.</Muted>
        </Card>
      ) : (
        [...groups.values()].map((g) => (
          <View key={g.title} style={{ gap: space(2) }}>
            <Heading>{g.title}</Heading>
            {g.items.map((m) => (
              <Card key={`${g.title}/${m.name}`} style={{ gap: space(1) }}>
                <Text style={styles.name}>{m.name}</Text>
                {m.offer && <Text style={styles.offer}>{m.offer}</Text>}
                {m.place && (
                  <View style={styles.line}>
                    <MapPin color={colors.muted} size={14} />
                    <Text style={styles.meta}>{m.place}</Text>
                  </View>
                )}
                {m.hours && (
                  <View style={styles.line}>
                    <Clock color={colors.muted} size={14} />
                    <Text style={styles.meta}>{m.hours}</Text>
                  </View>
                )}
              </Card>
            ))}
          </View>
        ))
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  name: { fontSize: 16, fontWeight: "700", color: colors.forestDark },
  offer: { fontSize: 14, color: colors.textSoft },
  line: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  meta: { fontSize: 12, color: colors.muted, flexShrink: 1 },
});
