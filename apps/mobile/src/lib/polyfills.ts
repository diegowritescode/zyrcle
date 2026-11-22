/**
 * viem (through @noble) creates keys with crypto.getRandomValues, which React Native does not
 * always provide. expo-crypto fills it from the OS's secure random generator. Imported first, from
 * the root layout.
 */
import { getRandomValues } from "expo-crypto";

const g = globalThis as { crypto?: { getRandomValues?: unknown } };
if (typeof g.crypto?.getRandomValues !== "function") {
  g.crypto = { ...(g.crypto ?? {}), getRandomValues };
}
