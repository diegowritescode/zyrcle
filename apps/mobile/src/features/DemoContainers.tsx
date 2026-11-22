import { useQuery } from "@tanstack/react-query";
import { MATERIALS, familyOf } from "@zyrcle/client";
import { Recycle } from "lucide-react-native";
import { StyleSheet, Text, View } from "react-native";
import { api } from "@/lib/api";
import { WEB_URL } from "@/lib/config";
import { Button, Card, Heading, Muted, Pill } from "@/ui/kit";
import { colors, familyColor, space } from "@/ui/theme";

/**
 * The demo has no physical containers: these are simulated, with every sensor. "Usar" takes the QR
 * their screen is showing right now; scanning the screen from the web does the same through the camera.
 */
export function DemoContainers({ onPick, disabled }: { onPick: (qr: string) => void; disabled: boolean }) {
  const { data, isError } = useQuery({ queryKey: ["demo-containers"], queryFn: api.demo.containers, refetchInterval: 3_000 });

  return (
    <Card style={{ gap: space(3) }}>
      <Heading>Contenedores de la demo</Heading>
      <Muted>
        Abre la pantalla de uno en tu computador ({WEB_URL.replace("https://", "")}/container/ctr-0001) y
        escanéala, o toca «Usar».
      </Muted>
      {isError && <Muted style={{ color: colors.danger }}>No pudimos cargar los contenedores.</Muted>}
      {(data ?? []).map((c) => (
        <View key={c.id} style={styles.row}>
          <Recycle color={familyColor[familyOf(c.accepted_materials).key]} size={22} />
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={styles.name}>{c.name}</Text>
            <Muted>{c.accepted_materials.map((m) => MATERIALS[m] ?? m).join(" · ")}</Muted>
          </View>
          {c.busy || !c.online ? (
            <Pill label={c.online ? "En uso" : "Sin conexión"} tone={c.online ? "busy" : "off"} />
          ) : (
            <Button
              title="Usar"
              disabled={disabled || !c.qr}
              onPress={() => c.qr && onPick(c.qr)}
              style={{ minHeight: 40, paddingHorizontal: space(4) }}
            />
          )}
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(3), paddingVertical: space(1) },
  name: { fontSize: 15, fontWeight: "600", color: colors.forestDark },
});
