import { pesos, shortHex } from "@zyrcle/client";
import * as Clipboard from "expo-clipboard";
import Constants from "expo-constants";
import * as WebBrowser from "expo-web-browser";
import { BookOpen, Check, Copy, ExternalLink, KeyRound, LayoutDashboard } from "lucide-react-native";
import { useState } from "react";
import { Alert, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { CHAIN_ID, REPO_URL, WEB_URL } from "@/lib/config";
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

  const reset = () => {
    const run = () => wallet.reset();
    const message = "Es una red de prueba: la wallet actual y su saldo se pierden en este teléfono.";
    if (Platform.OS === "web") {
      if (globalThis.confirm?.(message)) run();
      return;
    }
    Alert.alert("¿Crear otra wallet de prueba?", message, [
      { text: "Cancelar", style: "cancel" },
      { text: "Crear otra", style: "destructive", onPress: run },
    ]);
  };

  return (
    <Screen>
      <Title>Cuenta</Title>

      <Card style={{ gap: space(3) }}>
        <Heading>Tu wallet</Heading>
        <Body>
          Vive solo en este teléfono, guardada en su almacenamiento seguro. No tienes que anotar frases
          ni contraseñas: con ella recibes tus pagos.
        </Body>
        <Pressable accessibilityRole="button" accessibilityLabel="Copiar dirección" onPress={copy} style={styles.address}>
          <Text style={styles.addressText} selectable>
            {wallet.address ? shortHex(wallet.address) : "Creando…"}
          </Text>
          {copied ? <Check color={colors.emerald} size={18} /> : <Copy color={colors.forest} size={18} />}
        </Pressable>
        <Muted>Saldo: {wallet.balance === null ? "—" : pesos(wallet.balance)} en ZYR</Muted>
      </Card>

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

      <Button title="Crear otra wallet de prueba" variant="outline" icon={<KeyRound color={colors.forest} size={18} />} onPress={reset} />
      <Muted style={{ textAlign: "center" }}>Zyrcle {Constants.expoConfig?.version ?? ""}</Muted>
    </Screen>
  );
}

const styles = StyleSheet.create({
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
