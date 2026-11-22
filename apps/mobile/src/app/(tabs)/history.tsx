import { useQuery } from "@tanstack/react-query";
import { pesos } from "@zyrcle/client";
import { router } from "expo-router";
import { View } from "react-native";
import { DepositRow } from "@/features/DepositRow";
import { api } from "@/lib/api";
import { Button, Card, Muted, Title } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

export default function HistoryScreen() {
  const { token } = useWallet();
  const me = useQuery({
    queryKey: ["me", token],
    queryFn: () => api.me(token!),
    enabled: token !== null,
    refetchInterval: 15_000,
  });
  const sessions = me.data?.sessions ?? [];
  const paid = sessions.reduce((sum, s) => sum + (s.payout?.status === "confirmed" ? s.payout.amount_cop : 0), 0);

  return (
    <Screen refreshing={me.isRefetching} onRefresh={() => me.refetch()}>
      <View>
        <Title>Mis depósitos</Title>
        <Muted>Tus últimos 20 depósitos{paid > 0 ? ` · ${pesos(paid)} recibidos` : ""}</Muted>
      </View>
      <Card style={{ paddingVertical: space(2) }}>
        {me.isLoading || token === null ? (
          <Muted style={{ paddingVertical: space(3) }}>Cargando…</Muted>
        ) : sessions.length === 0 ? (
          <View style={{ gap: space(3), paddingVertical: space(3) }}>
            <Muted>Todavía no has reciclado con esta wallet.</Muted>
            <Button title="Reciclar ahora" onPress={() => router.push("/scan")} />
          </View>
        ) : (
          sessions.map((entry, i) => (
            <View key={entry.id} style={i > 0 ? { borderTopWidth: 1, borderTopColor: colors.border } : undefined}>
              <DepositRow entry={entry} />
            </View>
          ))
        )}
      </Card>
    </Screen>
  );
}
