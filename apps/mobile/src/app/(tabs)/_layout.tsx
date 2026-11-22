import { Tabs } from "expo-router";
import { CalendarClock, History, House, Wallet } from "lucide-react-native";
import { colors } from "@/ui/theme";

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.emerald,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: { backgroundColor: colors.white, borderTopColor: colors.border },
        tabBarLabelStyle: { fontWeight: "600" },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Inicio", tabBarIcon: ({ color, size }) => <House color={color} size={size} /> }} />
      <Tabs.Screen
        name="turns"
        options={{ title: "Turnos", tabBarIcon: ({ color, size }) => <CalendarClock color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="history"
        options={{ title: "Depósitos", tabBarIcon: ({ color, size }) => <History color={color} size={size} /> }}
      />
      <Tabs.Screen name="account" options={{ title: "Cuenta", tabBarIcon: ({ color, size }) => <Wallet color={color} size={size} /> }} />
    </Tabs>
  );
}
