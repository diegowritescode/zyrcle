import { useQuery, useQueryClient } from "@tanstack/react-query";
import { paymentErrorMessage, pesos } from "@zyrcle/client";
import * as Haptics from "expo-haptics";
import { router, useLocalSearchParams } from "expo-router";
import { CheckCircle2, Store } from "lucide-react-native";
import { useEffect, useState } from "react";
import { Platform, StyleSheet, Text, View } from "react-native";
import { api } from "@/lib/api";
import { Body, Button, Card, Heading, Muted, Notice } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

/** Pay a merchant's charge from this phone's account (docs/adr/0029). The phone signs; the
 * backend relays and pays the gas. */
export default function Pay() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { token, balance, signExecute, refreshBalance } = useWallet();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const payment = useQuery({
    queryKey: ["payment", id],
    queryFn: () => api.payment(token!, id!),
    enabled: token !== null && !!id,
    refetchInterval: (q) => (q.state.data?.status === "paying" ? 1_500 : false),
  });
  const p = payment.data;

  const pay = async () => {
    if (!token || !p) return;
    setBusy(true);
    setError(null);
    try {
      const typed = await api.paymentIntent(token, p.id);
      const signed = await signExecute(typed);
      await api.pay(token, p.id, signed);
      await queryClient.invalidateQueries({ queryKey: ["payment", id] });
    } catch (e) {
      setError(paymentErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const paid = p?.status === "paid";
  useEffect(() => {
    if (!paid) return;
    if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    refreshBalance();
  }, [paid, refreshBalance]);

  return (
    <Screen>
      {error && <Notice text={error} />}
      {!p ? (
        <Muted>{payment.isError ? "No encontramos ese cobro." : "Cargando el cobro…"}</Muted>
      ) : (
        <Card style={{ gap: space(3), alignItems: "center" }}>
          {p.status === "paid" ? <CheckCircle2 color={colors.emerald} size={48} /> : <Store color={colors.emerald} size={40} />}
          <Heading style={{ textAlign: "center" }}>{p.merchant}</Heading>
          <Text style={styles.amount}>{pesos(p.amount_cop)}</Text>
          <Muted>{p.concept}</Muted>
          {p.status === "open" && (
            <>
              <Body style={{ textAlign: "center" }}>
                Se paga desde tu cuenta, en ZYR. Tu saldo: {balance === null ? "—" : pesos(balance)}.
              </Body>
              <View style={{ alignSelf: "stretch", gap: space(2) }}>
                <Button title={`Pagar ${pesos(p.amount_cop)}`} loading={busy} onPress={pay} />
                <Button title="Cancelar" variant="outline" onPress={() => router.back()} />
              </View>
            </>
          )}
          {p.status === "paying" && <Muted>Pagando… tarda unos segundos.</Muted>}
          {p.status === "paid" && (
            <>
              <Body>Pagado.</Body>
              <Button title="Listo" onPress={() => router.replace("/")} style={{ alignSelf: "stretch" }} />
            </>
          )}
          {p.status === "expired" && <Notice text="Este cobro venció. Pide al comercio uno nuevo." tone="warn" />}
          {p.status === "failed" && <Notice text="El pago no se pudo hacer. No se descontó nada." tone="warn" />}
        </Card>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  amount: { fontSize: 36, fontWeight: "800", color: colors.forestDark },
});
