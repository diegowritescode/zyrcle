/**
 * Notifications (docs/adr/0008-push-notifications.md).
 *
 * - Push, sent by the API through Expo: payments and deposit reviews, which happen while the app
 *   may be closed. Needs a development or store build: Expo Go on Android has no remote push.
 * - Local, scheduled on this phone: the reminder 10 minutes before a booked turn. The wallet lives
 *   only on this phone, so every booking was made here and the phone can keep the reminders in step
 *   with the API on its own, even offline. Works in Expo Go too.
 */
import type { Booking } from "@zyrcle/client";
import { hourLabel } from "@zyrcle/client";
import Constants, { ExecutionEnvironment } from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { AndroidImportance, IosAuthorizationStatus } from "expo-notifications";
import { Platform } from "react-native";

export type PushSupport = "ok" | "web" | "emulator" | "expo-go" | "unconfigured";
export type Permission = "granted" | "denied" | "undetermined";

/** Minutes before a booked turn to remind the resident. */
export const REMINDER_MINUTES = 10;
const REMINDER_PREFIX = "turn-";

const native = Platform.OS !== "web";
const projectId: string | undefined =
  Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId ?? undefined;

if (native) {
  // Show notifications that arrive while the app is open too: a payment is good news either way.
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}

/** Whether this build can receive push notifications, and if not, why. */
export function pushSupport(): PushSupport {
  if (!native) return "web";
  if (!Device.isDevice) return "emulator";
  if (Platform.OS === "android" && Constants.executionEnvironment === ExecutionEnvironment.StoreClient) {
    return "expo-go";
  }
  if (!projectId) return "unconfigured";
  return "ok";
}

/** Android channels, one per kind, so the resident can mute reminders and keep payments. The API
 * names them (notifications.py).
 *
 * Never throws: Expo Go on Android rejects every channel call (its build lacks the native channel
 * provider, a NullPointerException). Notifications still show there, in expo-notifications'
 * fallback channel, so a failure here must not stop the permission request. */
export async function setUpChannels(): Promise<void> {
  if (Platform.OS !== "android") return;
  const { HIGH, DEFAULT } = AndroidImportance;
  const results = await Promise.allSettled([
    Notifications.setNotificationChannelAsync("payments", { name: "Pagos", importance: HIGH, lightColor: "#10B981" }),
    Notifications.setNotificationChannelAsync("deposits", { name: "Depósitos en revisión", importance: DEFAULT }),
    Notifications.setNotificationChannelAsync("turns", { name: "Recordatorios de turno", importance: HIGH }),
    Notifications.setNotificationChannelAsync("account", { name: "Seguridad de tu cuenta", importance: HIGH }),
  ]);
  const failed = results.find((r) => r.status === "rejected");
  if (failed && Constants.executionEnvironment !== ExecutionEnvironment.StoreClient) {
    console.log("could not create notification channels", failed.reason);
  }
}

function toPermission(p: Notifications.NotificationPermissionsStatus): Permission {
  if (p.granted || p.ios?.status === IosAuthorizationStatus.PROVISIONAL) return "granted";
  return p.canAskAgain ? "undetermined" : "denied";
}

export async function getPermission(): Promise<Permission> {
  if (!native) return "denied";
  return toPermission(await Notifications.getPermissionsAsync());
}

export async function requestPermission(): Promise<Permission> {
  if (!native) return "denied";
  await setUpChannels();
  return toPermission(await Notifications.requestPermissionsAsync());
}

/** This installation's Expo push token, which the API sends to. */
export async function expoPushToken(): Promise<string> {
  return (await Notifications.getExpoPushTokenAsync({ projectId })).data;
}

/**
 * Make the scheduled reminders match the upcoming bookings: schedule the missing ones, cancel
 * those whose booking is gone. Idempotent, so it runs whenever the bookings change.
 */
export async function syncTurnReminders(bookings: Booking[]): Promise<void> {
  if (!native) return;
  const wanted = new Map(
    bookings.filter((b) => b.state === "upcoming").map((b) => [`${REMINDER_PREFIX}${b.id}`, b]),
  );
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  const have = new Set<string>();
  for (const n of scheduled) {
    if (!n.identifier.startsWith(REMINDER_PREFIX)) continue;
    if (wanted.has(n.identifier)) have.add(n.identifier);
    else await Notifications.cancelScheduledNotificationAsync(n.identifier);
  }
  for (const [identifier, b] of wanted) {
    const at = new Date(b.starts_at).getTime() - REMINDER_MINUTES * 60_000;
    if (have.has(identifier) || at <= Date.now() + 5_000) continue;
    await Notifications.scheduleNotificationAsync({
      identifier,
      content: {
        title: `Tu turno empieza a las ${hourLabel(b.hour)}`,
        body: `${b.container_name} · ${b.residence_name}. Lleva tu material separado.`,
        data: { url: "/turns", kind: "turn_reminder" },
        sound: "default",
      },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: at, channelId: "turns" },
    });
  }
}

/** Screens a notification may open (its `data.url`). */
export const NOTIFICATION_ROUTES = new Set(["/history", "/turns", "/"]);
