import { useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, exportPeriods, paymentErrorMessage, pesos, type ExportFormat, type Payment, type Redemption } from "@zyrcle/client";
import { Banknote, FileSpreadsheet, Plus } from "lucide-react-native";
import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "@/lib/api";
import { handOver } from "@/lib/handOver";
import { Body, Button, Card, Chip, Heading, Muted, Notice, Pill } from "@/ui/kit";
import { QrCode } from "@/ui/QrCode";
import { Screen } from "@/ui/Screen";
import { colors, radius, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

const CHARGE: Record<Payment["status"], string> = { open: "Esperando", paying: "Pagando", paid: "Pagado", failed: "Falló", expired: "Venció" };
const REDEMPTION: Record<Redemption["status"], string> = {
  requested: "Enviando",
  pending: "Esperando la transferencia",
  settled: "Pagado en pesos",
  refunded: "Devuelto",
  failed: "Falló",
};

/** A campus merchant: charge with a QR, see payments, and turn ZYR into pesos (docs/adr/0029). */
export default function Shop() {
  const { token, balance, signExecute, refreshBalance } = useWallet();
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [concept, setConcept] = useState("");
  const [redeem, setRedeem] = useState("");
  const [current, setCurrent] = useState<Payment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const periods = exportPeriods(new Date());
  const [period, setPeriod] = useState(periods[0].label);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const home = useQuery({ queryKey: ["merchant", token], queryFn: () => api.merchant(token!), enabled: token !== null, refetchInterval: 3_000 });
  const live = home.data?.charges.find((c) => c.id === current?.id) ?? current;

  const run = async (job: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await job();
      await queryClient.invalidateQueries({ queryKey: ["merchant"] });
      refreshBalance();
    } catch (e) {
      setError(paymentErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const charge = () =>
    run(async () => {
      setCurrent(await api.charge(token!, Number(amount), concept));
      setAmount("");
      setConcept("");
    });
  const cashOut = () =>
    run(async () => {
      const intent = await api.redemptionIntent(token!, Number(redeem));
      await api.signRedemption(token!, intent.id, await signExecute(intent.typed_data));
      setRedeem("");
    });

  /** Charges and redemptions for the bookkeeping (docs/adr/0045). */
  const download = async (format: ExportFormat) => {
    setExporting(format);
    setError(null);
    try {
      const chosen = periods.find((p) => p.label === period) ?? periods[0];
      await handOver(await api.merchantExport(token!, chosen, format));
    } catch (e) {
      setError(paymentErrorMessage(e));
    } finally {
      setExporting(null);
    }
  };

  if (home.isError) {
    return (
      <Screen>
        <Notice text="Esta pantalla es para comercios del campus. Si tienes uno, pídele al operador que active tu cuenta." tone="info" />
      </Screen>
    );
  }

  return (
    <Screen>
      {home.data && <Muted>{home.data.name} · saldo {balance === null ? "—" : pesos(balance)}</Muted>}
      {error && <Notice text={error} />}

      {live && live.status !== "paid" && live.status !== "expired" ? (
        <Card style={{ gap: space(3), alignItems: "center" }}>
          <Heading>Cobro de {pesos(live.amount_cop)}</Heading>
          <QrCode value={live.qr} />
          <Muted>{live.concept} · {CHARGE[live.status]}</Muted>
          <Body style={{ textAlign: "center" }}>Que el cliente lo escanee con su app de Zyrcle. Vence en 10 minutos.</Body>
          <Button title="Cerrar" variant="outline" onPress={() => setCurrent(null)} style={{ alignSelf: "stretch" }} />
        </Card>
      ) : (
        <Card style={{ gap: space(3) }}>
          {live?.status === "paid" && <Notice text={`Recibiste ${pesos(live.amount_cop)}.`} tone="info" />}
          <Heading>Cobrar</Heading>
          <TextInput value={amount} onChangeText={setAmount} placeholder="Valor en pesos" keyboardType="number-pad" accessibilityLabel="Valor del cobro" style={styles.input} placeholderTextColor={colors.muted} />
          <TextInput value={concept} onChangeText={setConcept} placeholder="Concepto (opcional)" accessibilityLabel="Concepto" style={styles.input} placeholderTextColor={colors.muted} />
          <Button title="Generar QR" icon={<Plus color={colors.white} size={18} />} disabled={!(Number(amount) > 0) || busy} loading={busy} onPress={charge} />
        </Card>
      )}

      <Card style={{ gap: space(3) }}>
        <Heading>Cambiar ZYR a pesos</Heading>
        <Muted>Zyrcle te transfiere los pesos a tu cuenta bancaria y retira esos ZYR.</Muted>
        <TextInput value={redeem} onChangeText={setRedeem} placeholder="Cuántos pesos" keyboardType="number-pad" accessibilityLabel="Valor a cambiar" style={styles.input} placeholderTextColor={colors.muted} />
        <Button title="Solicitar el cambio" variant="outline" icon={<Banknote color={colors.forest} size={18} />} disabled={!(Number(redeem) > 0) || busy} onPress={cashOut} />
        {(home.data?.redemptions ?? []).map((r) => (
          <View key={r.id} style={styles.row}>
            <Text style={styles.rowText}>{pesos(r.amount_cop)} · {dateTime(r.created_at)}</Text>
            <Pill label={REDEMPTION[r.status]} tone={r.status === "settled" ? "ok" : r.status === "pending" ? "busy" : "off"} />
          </View>
        ))}
      </Card>

      <Card style={{ gap: space(2) }}>
        <Heading>Últimos cobros</Heading>
        {(home.data?.charges ?? []).length === 0 && <Muted>Aún no hay cobros.</Muted>}
        {(home.data?.charges ?? []).map((c) => (
          <View key={c.id} style={styles.row}>
            <Text style={styles.rowText}>{pesos(c.amount_cop)} · {c.concept}</Text>
            <Pill label={CHARGE[c.status]} tone={c.status === "paid" ? "ok" : c.status === "open" || c.status === "paying" ? "busy" : "off"} />
          </View>
        ))}
      </Card>

      <Card style={{ gap: space(3) }}>
        <Heading>Para tu contabilidad</Heading>
        <Muted>Tus cobros pagados y tus cambios a pesos, con tu NIT, las referencias y las transacciones.</Muted>
        <View style={styles.chips}>
          {periods.map((p) => (
            <Chip key={p.label} label={p.label} hint={`${p.start.slice(5)} a ${p.end.slice(5)}`} selected={p.label === period} onPress={() => setPeriod(p.label)} />
          ))}
        </View>
        <Button title="Descargar en Excel" icon={<FileSpreadsheet color={colors.white} size={18} />} loading={exporting === "xlsx"} disabled={exporting !== null} onPress={() => download("xlsx")} />
        <Button title="Descargar en CSV" variant="outline" loading={exporting === "csv"} disabled={exporting !== null} onPress={() => download("csv")} />
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: space(4),
    paddingVertical: space(3),
    fontSize: 17,
    color: colors.forestDark,
    backgroundColor: colors.white,
  },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space(2) },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space(2), paddingVertical: space(1) },
  rowText: { flex: 1, fontSize: 15, color: colors.forestDark },
});
