import { Alert, Platform } from "react-native";

/** A yes/no question. Alert has no buttons on the web build (used in tests), so it uses confirm(). */
export function confirm(
  title: string,
  message: string,
  ok: string,
  { destructive = false, cancel = "Cancelar" }: { destructive?: boolean; cancel?: string } = {},
): Promise<boolean> {
  if (Platform.OS === "web") return Promise.resolve(globalThis.confirm?.(`${title}\n\n${message}`) ?? false);
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: cancel, style: "cancel", onPress: () => resolve(false) },
      { text: ok, style: destructive ? "destructive" : "default", onPress: () => resolve(true) },
    ], { cancelable: true, onDismiss: () => resolve(false) }),
  );
}
