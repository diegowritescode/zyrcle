import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import { Body, Button, Title } from "@/ui/kit";
import { colors, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

/** A phone whose account was moved to another phone (a recovery) can only start a new one. */
export function RetiredGate({ children }: { children: ReactNode }) {
  const wallet = useWallet();
  if (!wallet.retired) return children;
  return (
    <View style={styles.screen}>
      <Title>Esta cuenta ya está en otro teléfono</Title>
      <Body>
        Tu cuenta y tu saldo pasaron a un teléfono nuevo, así que esta app ya no puede usarlos. Si quieres, empieza una
        cuenta nueva aquí.
      </Body>
      <Button title="Empezar una cuenta nueva" onPress={wallet.reset} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, justifyContent: "center", padding: space(6), gap: space(4), backgroundColor: colors.background },
});
