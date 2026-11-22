/** API session tokens, cached per address for this tab so a reload does not ask to sign again. */
import { isFresh } from "@zyrcle/client";

const key = (address: string) => `zyrcle:token:${address.toLowerCase()}`;

export function cachedToken(address: string, now = Date.now()): string | null {
  try {
    const token = sessionStorage.getItem(key(address));
    return token && isFresh(token, now) ? token : null;
  } catch {
    return null;
  }
}

export function cacheToken(address: string, token: string): void {
  try {
    sessionStorage.setItem(key(address), token);
  } catch {
    /* storage blocked: sign in again next time */
  }
}

export function forgetToken(address: string): void {
  try {
    sessionStorage.removeItem(key(address));
  } catch {
    /* ignore */
  }
}
