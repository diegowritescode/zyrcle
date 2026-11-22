import { useQuery } from "@tanstack/react-query";
import { ACTIVE, kg, pesos, shortHex } from "@zyrcle/client";
import { Image } from "expo-image";
import { router } from "expo-router";
import { CircleDollarSign, QrCode, Recycle, ShieldCheck } from "lucide-react-native";
import { StyleSheet, Text, View } from "react-native";
import { DepositRow } from "@/features/DepositRow";
import { api } from "@/lib/api";
import { Body, Button, Card, GradientCard, Heading, IconBadge, Muted, Pill } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

const STEPS = [
  { icon: QrCode, title: "Escanea el contenedor", text: "Su pantalla muestra un QR que cambia cada 30 segundos." },
  { icon: ShieldCheck, title: "Deposita y toca «Terminé»", text: "La báscula pesa en vivo y verifica que no sea una piedra." },
  { icon: CircleDollarSign, title: "Recibe tus pesos", text: "El anticipo llega en segundos; el resto, cuando se vende el material." },
];

export default function Home() {
  const wallet = useWallet();
  const me = useQuery({
    queryKey: ["me", wallet.token],
    queryFn: () => api.me(wallet.token!),
    enabled: wallet.token !== null,
    refetchInterval: 15_000,
  });
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: 30_000 });
  const open = me.data?.sessions.find((s) => ACTIVE.has(s.state));
  const recent = me.data?.sessions.slice(0, 3) ?? [];

  return (
    <Screen
      refreshing={me.isRefetching}
      onRefresh={() => {
        me.refetch();
        stats.refetch();
        wallet.refreshBalance();
      }}
    >
      <View style={styles.header}>
        <View style={styles.brand}>
          <Image source={require("@/assets/images/logo.png")} style={styles.logo} accessibilityIgnoresInvertColors />
          <Text style={styles.brandText}>ZYRCLE</Text>
        </View>
        <Pill label="Testnet" tone="info" />
      </View>

      <GradientCard>
        <Text style={styles.balanceLabel}>Tu saldo</Text>
        <Text style={styles.balance} accessibilityLabel={`Saldo ${wallet.balance ?? 0} pesos`}>
          {wallet.balance === null ? "—" : pesos(wallet.balance)}
        </Text>
        <Text style={styles.balanceNote}>
          en ZYR · 1 ZYR = 1 peso{wallet.address ? ` · ${shortHex(wallet.address)}` : ""}
        </Text>
      </GradientCard>

      {open && (
        <Card style={{ gap: space(3), borderColor: colors.emerald }}>
          <Heading>Tienes un depósito abierto</Heading>
          <Body>{open.container_name}: la tapa sigue abierta. Vuelve para terminarlo o se cerrará solo.</Body>
          <Button title="Volver al depósito" onPress={() => router.push({ pathname: "/deposit", params: { resume: open.id } })} />
        </Card>
      )}

      <Button
        title="Reciclar ahora"
        icon={<QrCode color={colors.white} size={20} />}
        onPress={() => router.push("/scan")}
        disabled={!wallet.token}
        loading={!wallet.token && wallet.signingIn}
        style={{ minHeight: 58 }}
      />

      <Card style={{ gap: space(4) }}>
        <Heading>Cómo funciona</Heading>
        {STEPS.map(({ icon: Icon, title, text }) => (
          <View key={title} style={styles.step}>
            <IconBadge size={40}>
              <Icon color={colors.white} size={20} />
            </IconBadge>
            <View style={{ flex: 1 }}>
              <Text style={styles.stepTitle}>{title}</Text>
              <Muted>{text}</Muted>
            </View>
          </View>
        ))}
      </Card>

      <Card>
        <View style={styles.rowBetween}>
          <Heading>Tus últimos depósitos</Heading>
          {recent.length > 0 && (
            <Text style={styles.link} onPress={() => router.push("/history")}>
              Ver todos
            </Text>
          )}
        </View>
        {recent.length === 0 ? (
          <Muted style={{ marginTop: space(2) }}>Todavía no has reciclado. Tu primer depósito aparecerá aquí.</Muted>
        ) : (
          recent.map((entry) => <DepositRow key={entry.id} entry={entry} />)
        )}
      </Card>

      {stats.data && (
        <Card style={styles.stats}>
          <Recycle color={colors.emerald} size={22} />
          <Muted style={{ flex: 1 }}>
            En la demo se han verificado {kg(stats.data.kg_verified)} y pagado {pesos(stats.data.paid_cop)} a{" "}
            {stats.data.residents} {stats.data.residents === 1 ? "residente" : "residentes"}.
          </Muted>
        </Card>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  brand: { flexDirection: "row", alignItems: "center", gap: space(2) },
  logo: { width: 40, height: 40 },
  brandText: { fontSize: 20, fontWeight: "700", color: colors.forest },
  balanceLabel: { color: "rgba(255,255,255,0.9)", fontSize: 14, fontWeight: "500" },
  balance: { color: colors.white, fontSize: 40, fontWeight: "700", marginTop: space(1), fontVariant: ["tabular-nums"] },
  balanceNote: { color: "rgba(255,255,255,0.85)", fontSize: 13, marginTop: space(1) },
  step: { flexDirection: "row", gap: space(3), alignItems: "center" },
  stepTitle: { fontSize: 15, fontWeight: "600", color: colors.forestDark },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  link: { color: colors.emerald, fontWeight: "600" },
  stats: { flexDirection: "row", gap: space(3), alignItems: "center" },
});
