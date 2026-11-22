/**
 * Small key-value store for secrets: the OS keychain (iOS) or keystore (Android) through
 * expo-secure-store. The web build, used only for development and tests, falls back to
 * localStorage.
 */
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const web = Platform.OS === "web";

export async function getSecret(key: string): Promise<string | null> {
  if (web) return globalThis.localStorage?.getItem(key) ?? null;
  return SecureStore.getItemAsync(key);
}

export async function setSecret(key: string, value: string): Promise<void> {
  if (web) return globalThis.localStorage?.setItem(key, value);
  await SecureStore.setItemAsync(key, value, {
    // Readable only while the phone is unlocked, and never copied to another device.
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function deleteSecret(key: string): Promise<void> {
  if (web) return globalThis.localStorage?.removeItem(key);
  await SecureStore.deleteItemAsync(key);
}
