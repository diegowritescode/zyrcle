import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  MATERIALS,
  grams,
  parseBagQr,
  parseContainerQr,
  parseManualCode,
  containerQr,
  type Bag,
  type Collection,
} from "@zyrcle/client";
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import * as Haptics from "expo-haptics";
import { CheckCircle2, PackageCheck, PackageOpen, ScanLine, Trash2, TriangleAlert, Weight } from "lucide-react-native";
import { useRef, useState } from "react";
import { Platform, StyleSheet, Text, TextInput, View } from "react-native";
import { ContainersCard, EarningsCard } from "@/features/CollectorBoard";
import { DemoContainers } from "@/features/DemoContainers";
import { api } from "@/lib/api";
import { Body, Button, Card, Heading, Muted, Notice, Pill } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, radius, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

/** The material in each pile inside a simulated container, by the camera label of its items. */
const PILE: Record<string, string> = { pet: "pet", hdpe: "hdpe", metal: "metal", glass: "glass", paper: "paper", cardboard: "cardboard" };
// Mass balances hold within the larger of 50 g and 2 % (docs/adr/0012).
const balanced = (expected: number, measured: number) => Math.abs(expected - measured) <= Math.max(50, Math.round(Math.abs(expected) * 0.02));

const haptic = () => Platform.OS !== "web" && Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

function errorText(e: unknown): string {
  return e instanceof ApiError || e instanceof Error ? e.message : String(e);
}

/** A collector empties a container into bags, each weighed by the container's own scale (docs/adr/0012). */
export default function Collect() {
  const { token } = useWallet();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // What the camera is reading for: a container to open, or a bag to fill.
  const [scanning, setScanning] = useState<"container" | "bag" | null>(null);
  const [closedView, setClosedView] = useState<Collection | null>(null);

  const home = useQuery({
    queryKey: ["collector", token],
    queryFn: () => api.collector(token!),
    enabled: token !== null,
    refetchInterval: 5_000,
  });
  const currentId = home.data?.current?.id ?? closedView?.id ?? null;
  const live = useQuery({
    queryKey: ["collection", currentId],
    queryFn: () => api.collection(token!, currentId!),
    enabled: token !== null && currentId !== null,
    // The scale reports twice a second; the collector watches the weight drop as they empty.
    refetchInterval: (q) => (q.state.data && ["closed", "expired", "failed"].includes(q.state.data.state) ? false : 1_000),
  });
  const c = live.data ?? home.data?.current ?? null;

  const run = async (job: () => Promise<unknown>) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await job();
      await queryClient.invalidateQueries({ queryKey: ["collector"] });
      await queryClient.invalidateQueries({ queryKey: ["collection"] });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const openContainer = (raw: string) =>
    run(async () => {
      const parsed = parseContainerQr(raw) ?? parseManualCode(raw);
      if (!parsed) throw new Error("Ese no es el QR de un contenedor de Zyrcle.");
      setScanning(null);
      setClosedView(null);
      await api.startCollection(token!, containerQr(parsed.containerId, parsed.code));
      haptic();
    });

  const fill = (raw: string | null) =>
    run(async () => {
      if (!c) return;
      let bag: string | null = null;
      if (raw !== null) {
        bag = parseBagQr(raw);
        if (!bag) throw new Error("Ese no es el QR de una bolsa de Zyrcle.");
      }
      setScanning(null);
      await api.addFill(token!, c.id, bag);
      haptic();
    });

  const doneFill = () => run(async () => c?.open_fill_id && api.finishFill(token!, c.id, c.open_fill_id));
  const finish = () =>
    run(async () => {
      if (!c) return;
      const view = await api.finishCollection(token!, c.id);
      setClosedView(view); // keep showing it until the measurement arrives
    });
  const seal = (bag: Bag) => run(async () => api.sealBag(token!, bag.code));

  if (home.isError) {
    return (
      <Screen>
        <Notice text="Esta pantalla es para recolectores. Si lo eres, pídele al operador que active tu cuenta." tone="info" />
      </Screen>
    );
  }

  const openFill = c?.fills.find((f) => f.id === c.open_fill_id) ?? null;
  const closed = c?.state === "closed";

  return (
    <Screen>
      {home.data && <Muted>{home.data.name}</Muted>}
      {error && <Notice text={error} />}

      {scanning && <Scanner what={scanning} onRead={scanning === "container" ? openContainer : fill} onCancel={() => setScanning(null)} busy={busy} />}

      {!c && !scanning && (
        <Card style={{ gap: space(3) }}>
          <Heading>Vaciar un contenedor</Heading>
          <Body>Escanea el QR de su pantalla. Se abre, y vas sacando un material a la vez, cada uno a su bolsa.</Body>
          <Button title="Escanear contenedor" icon={<ScanLine color={colors.white} size={18} />} onPress={() => setScanning("container")} />
        </Card>
      )}
      {!c && !scanning && <ContainersCard containers={home.data?.containers ?? []} />}
      {!c && !scanning && <DemoContainers onPick={openContainer} disabled={busy} />}

      {c && (
        <Card style={{ gap: space(3) }}>
          <View style={styles.row}>
            <Heading style={{ flex: 1 }}>{c.container_name}</Heading>
            <Pill label={STATE_LABEL[c.state]} tone={c.state === "open" ? "ok" : c.state === "closed" ? "off" : "busy"} />
          </View>
          <View style={styles.row}>
            <Weight color={colors.forest} size={22} />
            {/* An empty scale reads a few grams either side of zero. */}
            <Text style={styles.weight} accessibilityLabel={`Peso ${Math.max(c.weight_g ?? 0, 0)} gramos`}>
              {c.weight_g === null ? "—" : grams(Math.max(c.weight_g, 0))}
            </Text>
            <Muted>en el contenedor</Muted>
          </View>

          {c.state === "authorized" && <Muted>Abriendo el contenedor…</Muted>}

          {c.fills.map((f) => (
            <View key={f.id} style={styles.fill}>
              {f.residue ? <Trash2 color={colors.muted} size={18} /> : <PackageOpen color={colors.emerald} size={18} />}
              <Text style={styles.fillText}>
                {f.residue ? "Residuo" : `${MATERIALS[f.material ?? ""] ?? f.material} · bolsa ${f.bag_code}`}
              </Text>
              <Text style={styles.fillGrams}>{f.done ? grams(f.grams ?? 0) : "sacando…"}</Text>
            </View>
          ))}

          {c.state === "open" && openFill && (
            <View style={{ gap: space(2) }}>
              <Body>
                {openFill.residue
                  ? "Saca lo que no se recicla (piedras, basura). Luego toca «Listo»."
                  : `Saca solo el ${MATERIALS[openFill.material ?? ""] ?? openFill.material} y ponlo en la bolsa. Luego toca «Listo».`}
              </Body>
              <DemoHands collection={c} kind={openFill.residue ? null : (PILE[openFill.material ?? ""] ?? null)} token={token} onError={setError} />
              <Button title="Listo" icon={<CheckCircle2 color={colors.white} size={18} />} loading={busy} onPress={doneFill} />
            </View>
          )}

          {c.state === "open" && !openFill && (
            <View style={{ gap: space(2) }}>
              <Button title="Escanear una bolsa" icon={<ScanLine color={colors.white} size={18} />} disabled={busy} onPress={() => setScanning("bag")} />
              <Button title="Sacar residuo" variant="outline" icon={<Trash2 color={colors.forest} size={18} />} disabled={busy} onPress={() => fill(null)} />
              <Button title="Terminar y cerrar" variant="outline" disabled={busy} onPress={finish} />
            </View>
          )}

          {c.state === "closing" && <Muted>Cerrando y tomando la medida final…</Muted>}
          {closed && <ClosedSummary c={c} onAgain={() => setClosedView(null)} />}
          {(c.state === "expired" || c.state === "failed") && (
            <Notice text="El contenedor no respondió. Lo que alcanzaste a pesar quedó guardado." tone="warn" />
          )}
        </Card>
      )}

      <BagsCard bags={home.data?.bags ?? []} onSeal={seal} busy={busy} />
      <EarningsCard token={token} />
    </Screen>
  );
}

const STATE_LABEL: Record<Collection["state"], string> = {
  authorized: "Abriendo",
  open: "Abierto",
  closing: "Cerrando",
  closed: "Cerrado",
  expired: "Sin respuesta",
  failed: "Sin medida",
};

function ClosedSummary({ c, onAgain }: { c: Collection; onAgain: () => void }) {
  const weighed = c.fills.reduce((sum, f) => sum + (f.grams ?? 0), 0);
  const ok = c.removed_g === null || balanced(c.removed_g, weighed);
  return (
    <View style={{ gap: space(2) }}>
      <Body>
        Salieron {grams(c.removed_g ?? 0)} del contenedor y pesaste {grams(weighed)} en bolsas y residuo.
      </Body>
      {ok ? (
        <Notice text="Cuadra: todo lo que salió quedó pesado." tone="info" />
      ) : (
        <Notice text="No cuadra: algo salió sin pesarse. El operador lo va a revisar antes de vender esas bolsas." tone="warn" />
      )}
      <Button title="Vaciar otro contenedor" variant="outline" onPress={onAgain} />
    </View>
  );
}

function BagsCard({ bags, onSeal, busy }: { bags: Bag[]; onSeal: (b: Bag) => void; busy: boolean }) {
  if (bags.length === 0) return null;
  return (
    <Card style={{ gap: space(3) }}>
      <Heading>Tus bolsas</Heading>
      <Muted>Cierra una bolsa cuando esté llena: queda lista para llevar al centro de acopio.</Muted>
      {bags.map((b) => (
        <View key={b.id} style={styles.fill}>
          {b.status === "sealed" ? <PackageCheck color={colors.emerald} size={20} /> : <PackageOpen color={colors.forest} size={20} />}
          <View style={{ flex: 1 }}>
            <Text style={styles.fillText}>
              {MATERIALS[b.material] ?? b.material} · {b.code}
            </Text>
            <Muted>{grams(b.grams)}</Muted>
          </View>
          {b.status === "sealed" ? (
            <Pill label="Cerrada" tone="ok" />
          ) : (
            <Button title="Cerrar" variant="outline" disabled={busy || b.grams <= 0} onPress={() => onSeal(b)} style={{ minHeight: 36, paddingHorizontal: space(3) }} />
          )}
        </View>
      ))}
    </Card>
  );
}

/** The demo has no hands: this takes the material out of the simulated container. */
function DemoHands({ collection, kind, token, onError }: { collection: Collection; kind: string | null; token: string | null; onError: (e: string) => void }) {
  const [done, setDone] = useState(false);
  const take = async () => {
    if (!token) return;
    try {
      await api.demo.takeOut(token, collection.id, kind);
      setDone(true);
    } catch (e) {
      onError(errorText(e));
    }
  };
  if (done) return <Muted>Listo en la demo: mira cómo baja el peso.</Muted>;
  return (
    <Button
      title={kind ? `Demo: sacar el ${MATERIALS[kind] ?? kind}` : "Demo: sacar todo lo demás"}
      variant="outline"
      onPress={take}
    />
  );
}

function Scanner({ what, onRead, onCancel, busy }: { what: "container" | "bag"; onRead: (raw: string) => void; onCancel: () => void; busy: boolean }) {
  const [permission, requestPermission] = useCameraPermissions();
  const [typed, setTyped] = useState("");
  const handling = useRef(false);
  const demoBags = useQuery({ queryKey: ["demo-bags"], queryFn: api.demo.bags, enabled: what === "bag" });

  const read = (raw: string) => {
    if (handling.current) return;
    handling.current = true;
    onRead(raw);
    setTimeout(() => (handling.current = false), 1500);
  };

  return (
    <Card style={{ gap: space(3) }}>
      <Heading>{what === "container" ? "Escanea el contenedor" : "Escanea la bolsa"}</Heading>
      {permission?.granted ? (
        <View style={styles.cameraBox}>
          <CameraView
            style={StyleSheet.absoluteFill}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            onBarcodeScanned={busy ? undefined : (r: BarcodeScanningResult) => read(r.data)}
          />
        </View>
      ) : (
        <Button title="Permitir la cámara" variant="outline" onPress={requestPermission} />
      )}
      <TextInput
        value={typed}
        onChangeText={setTyped}
        placeholder={what === "container" ? "ctr-0001 7KQ2MX" : "Código de la bolsa"}
        placeholderTextColor={colors.muted}
        autoCapitalize="characters"
        autoCorrect={false}
        accessibilityLabel={what === "container" ? "Código del contenedor" : "Código de la bolsa"}
        style={styles.input}
      />
      <Button title="Usar código" variant="outline" disabled={!typed.trim() || busy} onPress={() => read(typed)} />
      {what === "bag" && (demoBags.data ?? []).length > 0 && (
        <View style={{ gap: space(2) }}>
          <Muted>Bolsas de la demo (en la vida real llevan la etiqueta impresa):</Muted>
          {(demoBags.data ?? []).map((b) => (
            <Button key={b.id} title={`${MATERIALS[b.material] ?? b.material} · ${b.code}`} variant="outline" disabled={busy} onPress={() => read(b.qr)} />
          ))}
        </View>
      )}
      <Button title="Cancelar" variant="outline" onPress={onCancel} />
      {what === "container" && <TriangleAlertNote />}
    </Card>
  );
}

function TriangleAlertNote() {
  return (
    <View style={styles.row}>
      <TriangleAlert color={colors.muted} size={16} />
      <Muted style={{ flex: 1 }}>Nadie puede depositar mientras vacías el contenedor.</Muted>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(2) },
  weight: { fontSize: 28, fontWeight: "700", color: colors.forestDark },
  fill: { flexDirection: "row", alignItems: "center", gap: space(2), paddingVertical: space(1) },
  fillText: { flex: 1, fontSize: 15, color: colors.forestDark },
  fillGrams: { fontSize: 15, fontWeight: "600", color: colors.forestDark },
  cameraBox: { aspectRatio: 1, width: "100%", backgroundColor: "#000", borderRadius: radius.lg, overflow: "hidden" },
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
