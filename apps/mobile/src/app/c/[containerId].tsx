import { Redirect, useLocalSearchParams } from "expo-router";
import { containerQr } from "@zyrcle/client";

/**
 * Deep link: a container's QR is `zyrcle://c/<id>?code=<code>`, so scanning it with the phone's own
 * camera opens the app here (installed builds register the `zyrcle` scheme; Expo Go does not).
 */
export default function ContainerLink() {
  const { containerId, code } = useLocalSearchParams<{ containerId: string; code?: string }>();
  if (!containerId || !code) return <Redirect href="/scan" />;
  return <Redirect href={{ pathname: "/deposit", params: { qr: containerQr(containerId, code) } }} />;
}
