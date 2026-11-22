import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as Notifications from "expo-notifications";
import { router, type Href } from "expo-router";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AppState, Platform } from "react-native";
import { api } from "@/lib/api";
import {
  NOTIFICATION_ROUTES,
  expoPushToken,
  getPermission,
  pushSupport,
  requestPermission,
  setUpChannels,
  syncTurnReminders,
  type Permission,
} from "@/lib/notifications";
import { useWallet } from "@/wallet/context";
import { NotificationsContext, type NotificationsState } from "./context";

const push = pushSupport();
const native = Platform.OS !== "web";

function open(notification: Notifications.Notification) {
  const url = notification.request.content.data?.url;
  if (typeof url === "string" && NOTIFICATION_ROUTES.has(url)) router.push(url as Href);
}

/**
 * Registers this phone for push with the API, keeps the turn reminders in step with the bookings,
 * refreshes data when a notification arrives and opens the screen a tapped notification points to.
 */
export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { token, address } = useWallet();
  const queryClient = useQueryClient();
  const [permission, setPermission] = useState<Permission | null>(native ? null : "denied");

  // Read the permission at start and whenever the app comes back (it may have changed in Settings).
  useEffect(() => {
    if (!native) return;
    const read = () => getPermission().then(setPermission);
    setUpChannels().then(read);
    const sub = AppState.addEventListener("change", (s) => s === "active" && read());
    return () => sub.remove();
  }, []);

  const enable = useCallback(async () => {
    const result = await requestPermission();
    setPermission(result);
    return result;
  }, []);

  // Tell the API where to push, once per wallet and whenever the OS rotates the token.
  useEffect(() => {
    if (push !== "ok" || permission !== "granted" || !token) return;
    const register = () =>
      expoPushToken()
        .then((pushToken) => api.registerPushToken(token, pushToken, Platform.OS as "ios" | "android"))
        .catch((e) => console.warn("push registration failed", e));
    register();
    const sub = Notifications.addPushTokenListener(register);
    return () => sub.remove();
  }, [permission, token]);

  const bookings = useQuery({
    queryKey: ["bookings", token],
    queryFn: () => api.bookings(token!),
    enabled: token !== null,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (permission === "granted" && bookings.data) {
      syncTurnReminders(bookings.data).catch((e) => console.warn("could not schedule reminders", e));
    }
  }, [permission, bookings.data]);

  // A tap on a notification opens its screen, also when the tap is what launched the app.
  useEffect(() => {
    if (!native) return;
    const last = Notifications.getLastNotificationResponse();
    if (last?.notification) {
      open(last.notification);
      Notifications.clearLastNotificationResponse();
    }
    const sub = Notifications.addNotificationResponseReceivedListener((r) => open(r.notification));
    return () => sub.remove();
  }, []);

  // A push means the balance or a deposit changed: refresh them without waiting for the poll.
  useEffect(() => {
    if (!native) return;
    const sub = Notifications.addNotificationReceivedListener(() => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.invalidateQueries({ queryKey: ["account"] });
      queryClient.invalidateQueries({ queryKey: ["balance", address] });
    });
    return () => sub.remove();
  }, [queryClient, address]);

  const value = useMemo<NotificationsState>(() => ({ push, permission, enable }), [permission, enable]);
  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
}
