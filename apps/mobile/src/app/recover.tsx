import { useQueryClient } from "@tanstack/react-query";
import type { Recovery } from "@zyrcle/client";
import { router } from "expo-router";
import { CircleCheck, Hourglass } from "lucide-react-native";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { EmailCodeForm } from "@/account/EmailCodeForm";
import { useAccount } from "@/account/useAccount";
import { api } from "@/lib/api";
import { confirm } from "@/ui/confirm";
import { Body, Button, Card, Heading, IconBadge, Muted, Notice } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

const STEPS = [
  "Escribe el correo que confirmaste en tu teléfono anterior.",
  "Te enviamos un código a ese correo y lo escribes aquí.",
  "En 48 horas tu cuenta, tu saldo y tu historial pasan a este teléfono.",
];

/** Bring an older account to this phone (docs/adr/0010-smart-accounts-and-recovery.md). */
export default function Recover() {
  const { token } = useWallet();
  const account = useAccount();
  const queryClient = useQueryClient();
  const [started, setStarted] = useState<Recovery | null>(null);
  const live = account.data?.outgoing && ["starting", "waiting"].includes(account.data.outgoing.status);
  const waiting = (live ? account.data!.outgoing : null) ?? started;

  // The wait is over: this phone signed in again and is now the recovered account.
  if (account.data?.recovered_at) {
    return (
      <Screen>
        <View style={styles.center}>
          <IconBadge size={64}>
            <CircleCheck color={colors.white} size={30} />
          </IconBadge>
          <Heading style={{ textAlign: "center" }}>Recuperaste tu cuenta</Heading>
          <Body style={{ textAlign: "center" }}>Tu saldo, tu historial y tus turnos ya están en este teléfono.</Body>
        </View>
        <Button title="Ir al inicio" onPress={() => router.dismissTo("/")} />
      </Screen>
    );
  }

  if (waiting) {
    return (
      <Screen>
        <View style={styles.center}>
          <IconBadge size={64}>
            <Hourglass color={colors.white} size={30} />
          </IconBadge>
          <Heading style={{ textAlign: "center" }}>Tu cuenta llega el {waiting.ready_label}</Heading>
          <Body style={{ textAlign: "center" }}>
            Le avisamos al teléfono anterior y a tu correo. Esperamos 48 horas por seguridad: si alguien más lo pidió,
            quien tiene la cuenta puede cancelarlo. Te avisamos aquí cuando esté lista.
          </Body>
          <Muted style={{ textAlign: "center" }}>Mientras tanto no puedes depositar ni reservar desde este teléfono.</Muted>
        </View>
        <Button title="Volver al inicio" onPress={() => router.dismissTo("/")} />
      </Screen>
    );
  }

  const data = account.data;
  return (
    <Screen>
      <Body>Si perdiste tu teléfono, trae tu cuenta a este. Tu saldo nunca se mueve: solo cambia el teléfono que la controla.</Body>
      {data && !data.recovery_available && (
        <Notice tone="warn" text="La recuperación de cuentas todavía no está activa en el servidor." />
      )}
      {data && data.recovery_available && !data.can_recover && (
        <Notice
          tone="warn"
          text="Esta app ya tiene depósitos, turnos o un correo propios, así que no puede recibir otra cuenta. Usa la app recién instalada en tu teléfono nuevo."
        />
      )}
      {data?.can_recover && (
        <>
          <Card style={{ gap: space(3) }}>
            {STEPS.map((step, i) => (
              <View key={step} style={styles.step}>
                <Text style={styles.stepNumber}>{i + 1}</Text>
                <Body style={{ flex: 1 }}>{step}</Body>
              </View>
            ))}
          </Card>
          <Card>
            <EmailCodeForm
              send={(email) => api.sendRecoveryCode(token!, email)}
              submit={async (email, code) => {
                const ok = await confirm(
                  "¿Traer tu cuenta a este teléfono?",
                  "Le avisaremos al teléfono anterior y a tu correo. Durante 48 horas no podrás depositar ni reservar desde aquí.",
                  "Sí, traerla",
                );
                if (!ok) return;
                setStarted(await api.startRecovery(token!, email, code));
                await queryClient.invalidateQueries({ queryKey: ["account"] });
              }}
              submitLabel="Recuperar mi cuenta"
            />
          </Card>
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: "center", gap: space(4), paddingVertical: space(6) },
  step: { flexDirection: "row", gap: space(3), alignItems: "flex-start" },
  stepNumber: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.emeraldTint,
    color: colors.emeraldDark,
    fontWeight: "700",
    textAlign: "center",
    lineHeight: 28,
  },
});
