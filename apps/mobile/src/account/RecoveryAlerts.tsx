import { useQueryClient } from "@tanstack/react-query";
import { accountErrorMessage, type Recovery } from "@zyrcle/client";
import { Hourglass, ShieldAlert } from "lucide-react-native";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { api } from "@/lib/api";
import { confirm } from "@/ui/confirm";
import { Body, Button, Card, Heading, Notice } from "@/ui/kit";
import { colors, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";
import { useAccount } from "./useAccount";

const LIVE = new Set<Recovery["status"]>(["starting", "waiting"]);

/**
 * What the resident must know about a recovery (docs/adr/0010): someone moving their account to
 * another phone (with the button to stop it), or this phone waiting for an older account.
 */
export function RecoveryAlerts() {
  const { token } = useWallet();
  const account = useAccount();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const data = account.data;
  if (!data) return null;
  const { incoming, outgoing } = data;

  const cancel = async (id: string, title: string, message: string) => {
    if (!(await confirm(title, message, "Sí, cancelar", { destructive: true, cancel: "No" }))) return;
    setBusy(true);
    setError(null);
    try {
      await api.cancelRecovery(token!, id);
      await queryClient.invalidateQueries({ queryKey: ["account"] });
    } catch (e) {
      setError(accountErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {error && <Notice text={error} />}

      {incoming && LIVE.has(incoming.status) && (
        <Card style={[styles.card, styles.danger]}>
          <View style={styles.row}>
            <ShieldAlert color={colors.danger} size={22} />
            <Heading style={{ flex: 1 }}>¿Estás cambiando de teléfono?</Heading>
          </View>
          <Body>
            Tu cuenta pasará a otro teléfono el {incoming.ready_label} Si fuiste tú, no tienes que hacer
            nada. Si no fuiste tú, cancélalo ahora: tu saldo no se mueve.
          </Body>
          <Button
            title="No fui yo, cancelar"
            loading={busy}
            style={{ backgroundColor: colors.danger }}
            onPress={() =>
              cancel(incoming.id, "¿Cancelar la recuperación?", "Tu cuenta y tu saldo se quedan en este teléfono.")
            }
          />
        </Card>
      )}
      {incoming?.status === "cancelling" && <Notice tone="info" text="Cancelando la recuperación…" />}

      {outgoing && LIVE.has(outgoing.status) && (
        <Card style={styles.card}>
          <View style={styles.row}>
            <Hourglass color={colors.forest} size={22} />
            <Heading style={{ flex: 1 }}>Tu cuenta llega el {outgoing.ready_label}</Heading>
          </View>
          <Body>
            Esperamos 48 horas por seguridad: si otra persona lo pidió, quien tiene la cuenta puede cancelarlo. Mientras
            tanto no puedes depositar ni reservar turnos desde este teléfono.
          </Body>
          <Button
            title="Cancelar recuperación"
            variant="outline"
            loading={busy}
            onPress={() =>
              cancel(outgoing.id, "¿Cancelar la recuperación?", "Tu cuenta anterior se queda donde está.")
            }
          />
        </Card>
      )}
      {outgoing?.status === "cancelling" && <Notice tone="info" text="Cancelando la recuperación…" />}
      {outgoing?.status === "cancelled" && <Notice tone="warn" text={cancelledText(outgoing)} />}
      {outgoing?.status === "failed" && (
        <Notice text="No pudimos completar la recuperación. Escríbenos y te ayudamos." />
      )}

      {data.recovered_at && (
        <Notice tone="info" text="Recuperaste tu cuenta: tu saldo, tu historial y tus turnos ya están aquí." />
      )}
    </>
  );
}

function cancelledText(r: Recovery): string {
  if (r.cancelled_by === "new_phone") return "Cancelaste la recuperación.";
  if (r.cancelled_by === "replaced") return "Se pidió otra recuperación para esa cuenta, así que esta se canceló.";
  return "La recuperación se canceló desde el teléfono que tiene la cuenta.";
}

const styles = StyleSheet.create({
  card: { gap: space(3) },
  danger: { borderWidth: 1, borderColor: colors.danger, backgroundColor: colors.dangerTint },
  row: { flexDirection: "row", alignItems: "center", gap: space(2) },
});
