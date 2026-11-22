import { createContext, useContext } from "react";
import type { Permission, PushSupport } from "@/lib/notifications";

export interface NotificationsState {
  /** Whether this build can receive push notifications (Expo Go on Android cannot). */
  push: PushSupport;
  /** The OS permission, which local reminders need too. Null while it is being read. */
  permission: Permission | null;
  /** Ask for the permission (the OS prompt shows only once; after that, Settings). */
  enable: () => Promise<Permission>;
}

export const NotificationsContext = createContext<NotificationsState | null>(null);

export function useNotifications(): NotificationsState {
  const state = useContext(NotificationsContext);
  if (!state) throw new Error("useNotifications must be used inside <NotificationsProvider>");
  return state;
}
