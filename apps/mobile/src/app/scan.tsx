import { ApiError, containerQr, parseContainerQr, parseManualCode, parsePaymentQr } from "@zyrcle/client";
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { Camera, Keyboard } from "lucide-react-native";
import { useRef, useState } from "react";
import { Linking, Platform, StyleSheet, TextInput, View } from "react-native";
import { DemoContainers } from "@/features/DemoContainers";
import { api } from "@/lib/api";
import { Body, Button, Card, Heading, Muted, Notice } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, radius, space } from "@/ui/theme";

/** Read the container's QR (camera, typed code or a demo container) and go choose the material,
 * or a merchant's charge QR and go pay it. */
export default function Scan() {
  const [permission, requestPermission] = useCameraPermissions();
  const [manual, setManual] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const handling = useRef(false);

  const handle = async (raw: string) => {
    if (handling.current) return;
    handling.current = true;
    setBusy(true);
    setError(null);
    try {
      // A merchant's charge: pay it (docs/adr/0029).
      const paymentId = parsePaymentQr(raw);
      if (paymentId) {
        router.replace({ pathname: "/pay", params: { id: paymentId } });
        return;
      }
      const parsed = parseContainerQr(raw) ?? parseManualCode(raw);
      if (!parsed) {
        setError("Ese no es un código de Zyrcle. Escanea el QR de la pantalla del contenedor.");
        return;
      }
      await api.container(parsed.containerId); // fail here, not after choosing the material
      if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace({ pathname: "/deposit", params: { qr: containerQr(parsed.containerId, parsed.code) } });
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "Ese contenedor no existe." : e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      // Give the camera a moment before reading again, so one QR is not handled twice.
      setTimeout(() => (handling.current = false), 1500);
    }
  };

  return (
    <Screen edges={[]}>
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {permission?.granted ? (
          <View style={styles.cameraBox}>
            <CameraView
              style={StyleSheet.absoluteFill}
              facing="back"
              barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
              onBarcodeScanned={busy ? undefined : (r: BarcodeScanningResult) => handle(r.data)}
            />
            <View pointerEvents="none" style={styles.frame} />
          </View>
        ) : (
          <View style={styles.permission}>
            <Camera color={colors.emerald} size={40} />
            <Heading style={{ textAlign: "center" }}>Escanea el QR del contenedor</Heading>
            <Body style={{ textAlign: "center" }}>
              Zyrcle usa la cámara solo para leer el código de la pantalla del contenedor.
            </Body>
            {permission && !permission.granted && !permission.canAskAgain ? (
              <Button title="Abrir Ajustes" onPress={() => Linking.openSettings()} />
            ) : (
              <Button title="Permitir la cámara" onPress={requestPermission} />
            )}
          </View>
        )}
      </Card>

      {error && <Notice text={error} />}

      <Card style={{ gap: space(3) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: space(2) }}>
          <Keyboard color={colors.forest} size={18} />
          <Heading>¿Sin cámara?</Heading>
        </View>
        <Muted>Escribe el código que aparece debajo del QR, por ejemplo «ctr-0001 7KQ2MX».</Muted>
        <TextInput
          value={manual}
          onChangeText={setManual}
          placeholder="ctr-0001 7KQ2MX"
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="go"
          onSubmitEditing={() => manual.trim() && handle(manual)}
          accessibilityLabel="Código del contenedor"
          style={styles.input}
        />
        <Button title="Usar código" variant="outline" disabled={!manual.trim()} loading={busy} onPress={() => handle(manual)} />
      </Card>

      <DemoContainers onPick={handle} disabled={busy} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  cameraBox: { aspectRatio: 1, width: "100%", backgroundColor: "#000" },
  frame: {
    position: "absolute",
    top: "15%",
    left: "15%",
    right: "15%",
    bottom: "15%",
    borderWidth: 4,
    borderColor: "rgba(16,185,129,0.7)",
    borderRadius: radius.lg,
  },
  permission: { padding: space(6), gap: space(3), alignItems: "center" },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: space(4),
    paddingVertical: space(3),
    fontSize: 17,
    color: colors.forestDark,
    textAlign: "center",
    backgroundColor: colors.white,
  },
});
