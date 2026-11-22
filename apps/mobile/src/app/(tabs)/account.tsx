import { pesos, shortHex } from "@zyrcle/client";
import * as Clipboard from "expo-clipboard";
import Constants from "expo-constants";
import * as WebBrowser from "expo-web-browser";
import { Bell, BellOff, BookOpen, Check, Copy, ExternalLink, KeyRound, LayoutDashboard } from "lucide-react-native";
import { useState } from "react";
import { Linking, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { CHAIN_ID, REPO_URL, WEB_URL } from "@/lib/config";
import { REMINDER_MINUTES, sendTestNotification, type PushSupport } from "@/lib/notifications";
import { RecoveryAlerts } from "@/account/RecoveryAlerts";
import { RecoverCard, RecoveryEmailCard } from "@/account/RecoveryEmailCard";
import { useNotifications } from "@/notifications/context";
import { confirm } from "@/ui/confirm";
import { Body, Button, Card, Heading, Muted, Title } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, radius, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

function LinkRow({ icon, label, url }: { icon: React.ReactNode; label: string; url: string }) {
  return (
    <Pressable accessibilityRole="link" onPress={() => WebBrowser.openBrowserAsync(url)} style={styles.linkRow}>
      {icon}
      <Text style={styles.linkText}>{label}</Text>
      <ExternalLink color={colors.muted} size={16} />
    </Pressable>
  );
}

export default function Account() {
  const wallet = useWallet();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!wallet.address) return;
    await Clipboard.setStringAsync(wallet.address);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const reset = async () => {
    const ok = await confirm(
      "¿Crear otra cuenta de prueba?",
      "Es una red de prueba: esta cuenta y su saldo se pierden en este teléfono, salvo que tengas un correo de recuperación.",
      "Crear otra",
      { destructive: true },
    );
    if (ok) wallet.reset();
  };

  return (
    <Screen>
      <Title>Cuenta</Title>
      <RecoveryAlerts />

      <Card style={{ gap: space(3) }}>
        <Heading>Tu cuenta</Heading>
        <Body>
          Tu saldo vive en tu cuenta de Zyrcle, en la cadena. Este teléfono guarda la llave que la controla, en
          su almacenamiento seguro: no tienes que anotar frases ni contraseñas.
        </Body>
        <Pressable accessibilityRole="button" accessibilityLabel="Copiar dirección" onPress={copy} style={styles.address}>
          <Text style={styles.addressText} selectable>
            {wallet.address ? shortHex(wallet.address) : "Creando…"}
          </Text>
          {copied ? <Check color={colors.emerald} size={18} /> : <Copy color={colors.forest} size={18} />}
        </Pressable>
        <Muted>Saldo: {wallet.balance === null ? "—" : pesos(wallet.balance)} en ZYR</Muted>
      </Card>

      <RecoveryEmailCard />
      <RecoverCard />

      {Platform.OS !== "web" && <NotificationsCard />}

      <Card style={{ gap: space(2) }}>
        <Heading>Red</Heading>
        <Muted>ZyrcleChain, la L1 propia de Zyrcle en Avalanche Fuji (testnet) · Chain ID {CHAIN_ID}</Muted>
        <Muted>ZYR es su moneda: 1 ZYR = 1 peso. En la testnet no tiene valor real.</Muted>
      </Card>

      <Card style={{ paddingVertical: space(2) }}>
        <LinkRow icon={<LayoutDashboard color={colors.emerald} size={20} />} label="Panel de la residencia" url={`${WEB_URL}/residence`} />
        <View style={styles.divider} />
        <LinkRow icon={<BookOpen color={colors.emerald} size={20} />} label="Cómo funciona por dentro" url={`${REPO_URL}/blob/main/docs/architecture.md`} />
      </Card>

      <Button title="Crear otra cuenta de prueba" variant="outline" icon={<KeyRound color={colors.forest} size={18} />} onPress={reset} />
      <Muted style={{ textAlign: "center" }}>Zyrcle {Constants.expoConfig?.version ?? ""}</Muted>
    </Screen>
  );
}

/** Why push cannot arrive on this build, when it cannot. Turn reminders are local and still work. */
const PUSH_LIMIT: Record<Exclude<PushSupport, "ok" | "web">, string> = {
  "expo-go": "En Expo Go para Android solo llegan los recordatorios de turno. Los avisos de pagos necesitan la app instalada.",
  emulator: "En un emulador solo llegan los recordatorios de turno, no los avisos de pagos.",
  unconfigured: "Esta versión todavía no está conectada al servicio de notificaciones: solo llegan los recordatorios de turno.",
};

function NotificationsCard() {
  const { push, permission, enable } = useNotifications();
  const [testSent, setTestSent] = useState(false);
  const on = permission === "granted";
  return (
    <Card style={{ gap: space(3) }}>
      <View style={styles.row}>
        {on ? <Bell color={colors.emerald} size={20} /> : <BellOff color={colors.muted} size={20} />}
        <Heading style={{ flex: 1 }}>Notificaciones</Heading>
        <Text style={[styles.state, { color: on ? colors.emeraldDark : colors.muted }]}>
          {permission === null ? "…" : on ? "Activadas" : "Desactivadas"}
        </Text>
      </View>
      <Body>
        Te avisamos cuando te paguen, si un depósito queda en revisión y {REMINDER_MINUTES} minutos antes de cada turno.
      </Body>
      {on && push !== "ok" && push !== "web" && <Muted>{PUSH_LIMIT[push]}</Muted>}
      {on && (
        <>
          <Button
            title={testSent ? "Llega en 5 segundos…" : "Enviarme una de prueba"}
            variant="outline"
            disabled={testSent}
            onPress={async () => {
              await sendTestNotification(5);
              setTestSent(true);
              setTimeout(() => setTestSent(false), 6_000);
            }}
          />
          <Muted>Puedes salir de la app o bloquear el teléfono para verla como llegaría de verdad.</Muted>
        </>
      )}
      {permission === "undetermined" && <Button title="Activar notificaciones" onPress={enable} />}
      {permission === "denied" && (
        <>
          <Muted>Están bloqueadas en los ajustes del teléfono.</Muted>
          <Button title="Abrir Ajustes" variant="outline" onPress={() => Linking.openSettings()} />
        </>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(2) },
  state: { fontSize: 13, fontWeight: "600" },
  address: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.tint,
    borderRadius: radius.md,
    padding: space(3),
  },
  addressText: { fontFamily: Platform.select({ ios: "Menlo", default: "monospace" }), fontSize: 15, color: colors.forestDark },
  linkRow: { flexDirection: "row", alignItems: "center", gap: space(3), paddingVertical: space(3) },
  linkText: { flex: 1, fontSize: 15, fontWeight: "500", color: colors.forestDark },
  divider: { height: 1, backgroundColor: colors.border },
});
