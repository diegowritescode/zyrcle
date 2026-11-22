import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ACTIVE,
  ApiError,
  CREDITED,
  ITEMS,
  LID_OPEN,
  MATERIALS,
  PAYOUT_STATUS,
  STATES,
  familyOf,
  grams,
  parseContainerQr,
  pesos,
  shortHex,
  startErrorMessage,
  type ContainerInfo,
  type PayoutInfo,
  type Session,
} from "@zyrcle/client";
import * as Haptics from "expo-haptics";
import { router, Stack, useLocalSearchParams } from "expo-router";
import { CheckCircle2, Clock, Info, Recycle, Weight, XCircle } from "lucide-react-native";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { useDepositSession } from "@/hooks/useDepositSession";
import { api } from "@/lib/api";
import { Body, Button, Card, GradientCard, Heading, Muted, Notice, Pill, Title } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, familyColor, radius, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

const haptic = (type: Haptics.NotificationFeedbackType) => {
  if (Platform.OS !== "web") Haptics.notificationAsync(type);
};

export default function Deposit() {
  const { qr, resume } = useLocalSearchParams<{ qr?: string; resume?: string }>();
  const { token, ensureToken, refreshBalance } = useWallet();
  const queryClient = useQueryClient();
  const [material, setMaterial] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  const onPaid = useCallback(() => {
    refreshBalance();
    queryClient.invalidateQueries({ queryKey: ["me"] });
    haptic(Haptics.NotificationFeedbackType.Success);
  }, [refreshBalance, queryClient]);
  const deposit = useDepositSession(token, onPaid);
  const session = deposit.session;

  const containerId = session?.container_id ?? (qr ? parseContainerQr(qr)?.containerId : undefined);
  const container = useQuery({
    queryKey: ["container", containerId],
    queryFn: () => api.container(containerId!),
    enabled: !!containerId,
    refetchInterval: session ? false : 5_000,
  });

  // The first accepted material is preselected until the resident picks one.
  const chosen = material ?? container.data?.accepted_materials[0] ?? null;

  // Coming back to a deposit left open (from the home banner).
  const resumed = useRef(false);
  useEffect(() => {
    if (!resume || resumed.current) return;
    resumed.current = true;
    ensureToken()
      .then((t) => deposit.resume(t, resume))
      .catch((e) => setError(startErrorMessage(e)));
  }, [resume, ensureToken, deposit]);

  const open = async () => {
    if (!qr || !chosen) return;
    setOpening(true);
    setError(null);
    try {
      const t = await ensureToken();
      try {
        await deposit.start(t, qr, chosen);
      } catch (e) {
        if (e instanceof ApiError && /already have an open session/.test(e.message)) {
          const active = (await api.me(t)).sessions.find((s) => ACTIVE.has(s.state));
          if (active) return deposit.resume(t, active.id);
        }
        throw e;
      }
    } catch (e) {
      setError(startErrorMessage(e));
      haptic(Haptics.NotificationFeedbackType.Error);
    } finally {
      setOpening(false);
    }
  };

  const drop = (item: string) => {
    if (token && session) api.demo.drop(token, session.id, item).catch((e) => setError(startErrorMessage(e)));
  };

  const finish = async () => {
    if (!token || !session) return;
    setError(null);
    try {
      await api.finish(token, session.id);
    } catch (e) {
      setError(startErrorMessage(e));
    }
  };

  const final = session && !ACTIVE.has(session.state);
  useEffect(() => {
    if (!final || !session) return;
    haptic(CREDITED.has(session.state) ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning);
  }, [final, session?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Screen edges={["bottom"]}>
      <Stack.Screen options={{ title: session ? (final ? "Resultado" : "Depositando") : "Reciclar", gestureEnabled: !session || !!final }} />

      {container.data && <ContainerHeader container={container.data} />}
      {error && <Notice text={error} />}

      {session ? (
        final ? (
          <Result session={session} payout={deposit.payout} />
        ) : (
          <Live session={session} weight={deposit.weight} onDrop={drop} onFinish={finish} />
        )
      ) : resume ? (
        <ActivityIndicator color={colors.emerald} style={{ marginTop: space(10) }} />
      ) : (
        <Card style={{ gap: space(4) }}>
          <Heading>¿Qué vas a reciclar?</Heading>
          <View style={styles.choices} accessibilityRole="radiogroup">
            {(container.data?.accepted_materials ?? []).map((m) => (
              <Pressable
                key={m}
                accessibilityRole="radio"
                accessibilityState={{ checked: chosen === m }}
                onPress={() => setMaterial(m)}
                style={[styles.choice, chosen === m && styles.choiceOn]}
              >
                <Text style={[styles.choiceText, chosen === m && { color: colors.forestDark }]}>{MATERIALS[m] ?? m}</Text>
              </Pressable>
            ))}
          </View>
          <Button
            title="Abrir contenedor"
            icon={<Recycle color={colors.white} size={20} />}
            onPress={open}
            loading={opening}
            disabled={!chosen || !container.data?.online || container.data?.busy}
          />
          <Muted>El código del QR cambia cada 30 segundos. Si vence antes de abrir, vuelve a escanearlo.</Muted>
        </Card>
      )}

      {final && (
        <View style={{ gap: space(3) }}>
          <Button title="Reciclar otra vez" onPress={() => router.replace("/scan")} />
          <Button title="Volver al inicio" variant="outline" onPress={() => router.dismissTo("/")} />
        </View>
      )}
    </Screen>
  );
}

function ContainerHeader({ container }: { container: ContainerInfo }) {
  const status = !container.online ? (["Sin conexión", "off"] as const) : container.busy ? (["En uso", "busy"] as const) : (["Disponible", "ok"] as const);
  return (
    <GradientCard tone="soft" style={styles.containerCard}>
      <Recycle color={familyColor[familyOf(container.accepted_materials).key]} size={28} />
      <View style={{ flex: 1 }}>
        <Text style={styles.containerName}>{container.name}</Text>
        <Muted>{container.residence_name ?? container.accepted_materials.map((m) => MATERIALS[m] ?? m).join(" · ")}</Muted>
      </View>
      <Pill label={status[0]} tone={status[1]} />
    </GradientCard>
  );
}

function Live({ session, weight, onDrop, onFinish }: { session: Session; weight: number | null; onDrop: (item: string) => void; onFinish: () => void }) {
  const lidOpen = LID_OPEN.has(session.state);
  const items = useQuery({ queryKey: ["demo-items"], queryFn: api.demo.items, staleTime: Infinity });
  const added = weight !== null && session.tare_g !== null ? Math.max(0, weight - session.tare_g) : null;

  return (
    <Card style={{ gap: space(4), alignItems: "stretch" }}>
      <View style={{ alignItems: "center", gap: space(2) }}>
        {lidOpen ? <Recycle color={colors.emerald} size={48} /> : <ActivityIndicator color={colors.emerald} size="large" />}
        <Heading style={{ textAlign: "center" }}>{lidOpen ? "Tapa abierta: deposita tu material" : STATES[session.state]}</Heading>
        <Muted>
          Material declarado: {MATERIALS[session.declared_material] ?? session.declared_material}
          {lidOpen ? ` · ${STATES[session.state]}` : ""}
        </Muted>
      </View>

      <View style={styles.weight}>
        <Weight color={colors.emerald} size={26} />
        <View>
          <Muted>Llevas depositado</Muted>
          <Text style={styles.weightValue} accessibilityLiveRegion="polite">
            {added === null ? "—" : grams(added)}
          </Text>
        </View>
      </View>

      {lidOpen && (
        <>
          <View style={{ gap: space(2) }}>
            <Text style={styles.label}>
              Simula lo que tiras <Text style={{ fontWeight: "400", color: colors.muted }}>(en un contenedor real, lo tiras y ya)</Text>
            </Text>
            <View style={styles.items}>
              {(items.data ?? []).map((item) => {
                const trap = item.name === "stone" || item.name === "full_water_bottle";
                return (
                  <Pressable
                    key={item.name}
                    accessibilityRole="button"
                    onPress={() => onDrop(item.name)}
                    style={({ pressed }) => [styles.item, trap && styles.trap, pressed && { opacity: 0.7 }]}
                  >
                    <Text style={styles.itemName}>{ITEMS[item.name] ?? item.label}</Text>
                    <Muted>{grams(item.weight_g)}</Muted>
                  </Pressable>
                );
              })}
            </View>
          </View>
          <Button title="Terminé" icon={<CheckCircle2 color={colors.white} size={20} />} onPress={onFinish} />
          <Muted style={{ textAlign: "center" }}>Si te vas sin tocar «Terminé», el contenedor se cierra solo al minuto y te paga igual.</Muted>
        </>
      )}
    </Card>
  );
}

function Result({ session, payout }: { session: Session; payout: PayoutInfo | null }) {
  const credited = CREDITED.has(session.state);
  const Icon = credited ? CheckCircle2 : session.state === "review" ? Clock : session.state === "rejected" ? XCircle : Info;
  const tone = credited ? colors.emerald : session.state === "rejected" ? colors.danger : "#F59E0B";
  const pending = payout && !["confirmed", "failed", "deferred"].includes(payout.status);

  return (
    <View style={{ gap: space(4) }}>
      <Card style={{ alignItems: "center", gap: space(2) }}>
        <Icon color={tone} size={56} />
        <Title>{STATES[session.state] ?? session.state}</Title>
        <Muted>
          {MATERIALS[session.declared_material] ?? session.declared_material}
          {session.deposited_g !== null ? ` · ${grams(session.deposited_g)}` : ""}
          {session.score !== null ? ` · confianza ${Math.round(session.score * 100)} %` : ""}
        </Muted>
      </Card>

      {credited && (
        <GradientCard>
          <Text style={styles.payLabel}>Anticipo</Text>
          <Text style={styles.payAmount}>{payout ? pesos(payout.amount_cop) : "Calculando…"}</Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: space(2), marginTop: space(2) }}>
            {(pending || !payout) && <ActivityIndicator color={colors.white} size="small" />}
            <Text style={styles.payStatus}>{payout ? PAYOUT_STATUS[payout.status] ?? payout.status : "en cola para pagarse en la cadena"}</Text>
          </View>
          {payout?.tx_hash && <Text style={styles.payTx}>tx {shortHex(payout.tx_hash)}</Text>}
          <Text style={styles.payNote}>Hasta la mitad del valor estimado de tu material. El resto llega cuando se vende al centro de acopio.</Text>
        </GradientCard>
      )}

      {session.state === "review" && <Notice tone="warn" text="Algo no cuadró entre el peso y el volumen. Una persona revisa este depósito antes de pagarlo." />}
      {session.state === "rejected" && <Notice text="Este depósito no se pagará." />}
      {session.state === "empty" && <Notice tone="info" text="La báscula no registró material: no hay pago." />}
      {(session.state === "expired" || session.state === "failed") && (
        <Notice tone="info" text="El contenedor no respondió a tiempo. No se cobró nada; vuelve a intentarlo." />
      )}
      {session.reasons.length > 0 && (
        <Card style={{ gap: space(1) }}>
          <Text style={styles.label}>Detalle de la verificación</Text>
          {session.reasons.map((r) => (
            <Body key={r}>· {r}</Body>
          ))}
        </Card>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  containerCard: { flexDirection: "row", alignItems: "center", gap: space(3), borderWidth: 1, borderColor: "rgba(16,185,129,0.2)" },
  containerName: { fontSize: 17, fontWeight: "600", color: colors.forestDark },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: space(3) },
  choice: { flexGrow: 1, minWidth: "40%", borderWidth: 2, borderColor: colors.border, borderRadius: radius.lg, padding: space(4) },
  choiceOn: { borderColor: colors.emerald, backgroundColor: colors.emeraldTint },
  choiceText: { fontSize: 16, fontWeight: "600", color: colors.textSoft },
  weight: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(3),
    alignSelf: "center",
    backgroundColor: colors.tint,
    borderRadius: radius.lg,
    paddingHorizontal: space(6),
    paddingVertical: space(4),
  },
  weightValue: { fontSize: 34, fontWeight: "700", color: colors.forestDark, fontVariant: ["tabular-nums"] },
  label: { fontSize: 14, fontWeight: "600", color: colors.forest },
  items: { flexDirection: "row", flexWrap: "wrap", gap: space(2) },
  item: {
    width: "48.5%",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingVertical: space(3),
    alignItems: "center",
    gap: 2,
    backgroundColor: colors.white,
  },
  trap: { borderColor: "#FCD34D", backgroundColor: "#FFFBEB" },
  itemName: { fontSize: 14, fontWeight: "500", color: colors.forestDark, textAlign: "center" },
  payLabel: { color: "rgba(255,255,255,0.9)", fontSize: 14 },
  payAmount: { color: colors.white, fontSize: 36, fontWeight: "700", marginTop: space(1) },
  payStatus: { color: "rgba(255,255,255,0.95)", fontSize: 14 },
  payTx: { color: "rgba(255,255,255,0.85)", fontSize: 12, marginTop: space(1), fontFamily: Platform.select({ ios: "Menlo", default: "monospace" }) },
  payNote: { color: "rgba(255,255,255,0.85)", fontSize: 12, marginTop: space(3), lineHeight: 17 },
});
