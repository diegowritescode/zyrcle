/**
 * The push token loop of the first APK, and turn reminders kept in step with the bookings
 * (docs/adr/0008, 0015). expo-notifications and React Native are replaced by stand-ins.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const n = vi.hoisted(() => ({
  listeners: [] as ((token: { type: string; data: string }) => void)[],
  deviceToken: { type: "android", data: "fcm-1" },
  expoCalls: 0,
  scheduled: [] as { identifier: string }[],
  cancelled: [] as string[],
  added: [] as { identifier: string; trigger: { date: number } }[],
}));

vi.mock("react-native", () => ({ Platform: { OS: "android" } }));
vi.mock("expo", () => ({ isRunningInExpoGo: () => false }));
vi.mock("expo-constants", () => ({ default: { expoConfig: { extra: { eas: { projectId: "p" } } } } }));
vi.mock("expo-device", () => ({ isDevice: true }));
vi.mock("expo-notifications", () => ({
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
  IosAuthorizationStatus: { PROVISIONAL: 3 },
  SchedulableTriggerInputTypes: { DATE: "date", TIME_INTERVAL: "timeInterval" },
  setNotificationHandler: () => {},
  // Like expo-notifications 58: every native fetch also fires the token listeners.
  getDevicePushTokenAsync: async () => {
    const token = { ...n.deviceToken };
    for (const l of n.listeners) l(token);
    return token;
  },
  getExpoPushTokenAsync: async ({ devicePushToken }: { devicePushToken?: { data: string } }) => {
    n.expoCalls++;
    return { data: `ExponentPushToken[${devicePushToken?.data ?? "fetched"}]` };
  },
  addPushTokenListener: (l: (token: { type: string; data: string }) => void) => {
    n.listeners.push(l);
    return { remove: () => n.listeners.splice(n.listeners.indexOf(l), 1) };
  },
  getAllScheduledNotificationsAsync: async () => n.scheduled,
  cancelScheduledNotificationAsync: async (id: string) => void n.cancelled.push(id),
  scheduleNotificationAsync: async (req: { identifier: string; trigger: { date: number } }) => void n.added.push(req),
}));

const { keepPushTokenRegistered, syncTurnReminders, REMINDER_MINUTES } = await import("./notifications");
const settle = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  n.listeners.length = 0;
  n.deviceToken = { type: "android", data: "fcm-1" };
  n.expoCalls = 0;
  n.scheduled = [];
  n.cancelled = [];
  n.added = [];
});

describe("push token registration", () => {
  it("registers once, although every fetch fires the listener with the same token", async () => {
    const sent: string[] = [];
    const stop = keepPushTokenRegistered(async (t) => void sent.push(t));
    await settle();
    await settle();
    expect(sent).toEqual(["ExponentPushToken[fcm-1]"]);
    stop();
  });

  it("registers again only when Android hands over a different token", async () => {
    const sent: string[] = [];
    const stop = keepPushTokenRegistered(async (t) => void sent.push(t));
    await settle();
    n.listeners.forEach((l) => l({ type: "android", data: "fcm-1" }));
    n.listeners.forEach((l) => l({ type: "android", data: "fcm-2" }));
    await settle();
    expect(sent).toEqual(["ExponentPushToken[fcm-1]", "ExponentPushToken[fcm-2]"]);
    stop();
    expect(n.listeners).toHaveLength(0);
  });

  it("tries again after a failed registration", async () => {
    let fail = true;
    const sent: string[] = [];
    const stop = keepPushTokenRegistered(async (t) => {
      if (fail) throw new Error("offline");
      sent.push(t);
    });
    await settle();
    vi.spyOn(console, "warn").mockImplementation(() => {});
    fail = false;
    n.listeners.forEach((l) => l({ type: "android", data: "fcm-1" }));
    await settle();
    expect(sent).toEqual(["ExponentPushToken[fcm-1]"]);
    stop();
  });
});

describe("turn reminders", () => {
  const booking = (id: string, minutesAhead: number, state = "upcoming") => ({
    id,
    state,
    hour: 10,
    starts_at: new Date(Date.now() + minutesAhead * 60_000).toISOString(),
    container_name: "PET",
    site_name: "Campus Norte",
  });

  it("schedules missing reminders before the turn and cancels those whose booking is gone", async () => {
    n.scheduled = [{ identifier: "turn-old" }, { identifier: "turn-b" }, { identifier: "other" }];
    await syncTurnReminders([booking("a", 60), booking("b", 90), booking("c", 60, "cancelled")] as any);
    expect(n.cancelled).toEqual(["turn-old"]);
    expect(n.added.map((r) => r.identifier)).toEqual(["turn-a"]);
    const at = n.added[0].trigger.date;
    expect(Math.round((at - Date.now()) / 60_000)).toBe(60 - REMINDER_MINUTES);
  });

  it("skips a reminder whose moment has already passed", async () => {
    await syncTurnReminders([booking("soon", REMINDER_MINUTES - 1)] as any);
    expect(n.added).toHaveLength(0);
  });
});
