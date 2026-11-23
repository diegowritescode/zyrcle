import "@/lib/polyfills";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { RetiredGate } from "@/account/RetiredGate";
import { colors } from "@/ui/theme";
import { NotificationsProvider } from "@/notifications/NotificationsProvider";
import { WalletProvider } from "@/wallet/WalletProvider";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: false } },
});

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <WalletProvider>
        <NotificationsProvider>
          <StatusBar style="dark" />
          <RetiredGate>
          <Stack
            screenOptions={{
              headerTintColor: colors.forest,
              headerStyle: { backgroundColor: colors.background },
              headerShadowVisible: false,
              headerTitleStyle: { fontWeight: "600", color: colors.forestDark },
              contentStyle: { backgroundColor: colors.background },
              headerBackButtonDisplayMode: "minimal",
            }}
          >
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen name="scan" options={{ title: "Escanear contenedor", presentation: "modal" }} />
            <Stack.Screen name="deposit" options={{ title: "Reciclar" }} />
            <Stack.Screen name="c/[containerId]" options={{ headerShown: false }} />
            <Stack.Screen name="recover" options={{ title: "Recuperar tu cuenta" }} />
            <Stack.Screen name="collect" options={{ title: "Recolección" }} />
          </Stack>
          </RetiredGate>
        </NotificationsProvider>
      </WalletProvider>
    </QueryClientProvider>
  );
}
