import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { LifeBuoy, Mail, ShieldCheck } from "lucide-react-native";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { api } from "@/lib/api";
import { Body, Button, Card, Heading, Muted } from "@/ui/kit";
import { colors, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";
import { EmailCodeForm } from "./EmailCodeForm";
import { useAccount } from "./useAccount";

/** The email that lets the resident recover their account on another phone. */
export function RecoveryEmailCard() {
  const { token } = useWallet();
  const account = useAccount();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const data = account.data;
  if (!data?.email_available) return null;
  const confirmed = data.email !== null && !editing;

  return (
    <Card style={{ gap: space(3) }}>
      <View style={styles.row}>
        {confirmed ? <ShieldCheck color={colors.emerald} size={20} /> : <Mail color={colors.forest} size={20} />}
        <Heading style={{ flex: 1 }}>Correo de recuperación</Heading>
      </View>
      {confirmed ? (
        <>
          <Text style={styles.email} selectable>
            {data.email}
          </Text>
          <Muted>Si pierdes este teléfono, con este correo recuperas tu cuenta y tu saldo en uno nuevo.</Muted>
          <Button title="Cambiar correo" variant="outline" onPress={() => setEditing(true)} />
        </>
      ) : (
        <>
          <Body>
            Si pierdes este teléfono, con este correo recuperas tu cuenta y tu saldo en uno nuevo. Solo lo usamos para
            eso y para avisarte si alguien intenta llevarse tu cuenta.
          </Body>
          <EmailCodeForm
            send={(email) => api.sendEmailCode(token!, email)}
            submit={async (email, code) => {
              await api.verifyEmail(token!, email, code);
              setEditing(false);
              await queryClient.invalidateQueries({ queryKey: ["account"] });
            }}
            submitLabel="Confirmar correo"
            onCancel={editing ? () => setEditing(false) : undefined}
          />
        </>
      )}
    </Card>
  );
}

/** On a phone with no history of its own: bring an older account here. */
export function RecoverCard() {
  const account = useAccount();
  if (!account.data?.can_recover) return null;
  return (
    <Card style={{ gap: space(3) }}>
      <View style={styles.row}>
        <LifeBuoy color={colors.forest} size={20} />
        <Heading style={{ flex: 1 }}>¿Perdiste tu teléfono anterior?</Heading>
      </View>
      <Body>Trae a este teléfono tu cuenta, tu saldo y tu historial con el correo que confirmaste allá.</Body>
      <Button title="Recuperar mi cuenta" variant="outline" onPress={() => router.push("/recover")} />
    </Card>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(2) },
  email: { fontSize: 16, fontWeight: "600", color: colors.forestDark },
});
