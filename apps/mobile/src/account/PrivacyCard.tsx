import { useQueryClient } from "@tanstack/react-query";
import type { Me } from "@zyrcle/client";
import * as WebBrowser from "expo-web-browser";
import { ShieldCheck } from "lucide-react-native";
import { useState } from "react";
import { api } from "@/lib/api";
import { WEB_URL } from "@/lib/config";
import { Body, Button, Card, Heading, Muted } from "@/ui/kit";
import { colors, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

/** Asks for consent to the data-processing policy in force (Ley 1581 de 2012, docs/adr/0028),
 * until the participant accepts it. */
export function PrivacyCard({ me }: { me: Me | undefined }) {
  const { token } = useWallet();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  if (!me || me.privacy_version === me.privacy_current) return null;

  const accept = async () => {
    if (!token) return;
    setBusy(true);
    try {
      await api.acceptPrivacy(token, me.privacy_current);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card style={{ gap: space(3), borderColor: colors.emerald }}>
      <Heading>Tus datos</Heading>
      <Body>
        Usamos la dirección de tu cuenta, tus depósitos y, si los das, tu correo y tu teléfono para avisos, solo para
        pagarte y avisarte. Los pagos quedan en la cadena de bloques, sin tu nombre.
      </Body>
      <Button
        title="Leer la política completa"
        variant="outline"
        onPress={() => WebBrowser.openBrowserAsync(`${WEB_URL}/privacidad`)}
      />
      <Button title="Acepto" icon={<ShieldCheck color={colors.white} size={18} />} loading={busy} onPress={accept} />
      <Muted>Puedes revocarla cuando quieras. Versión {me.privacy_current}.</Muted>
    </Card>
  );
}
