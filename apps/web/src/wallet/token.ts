/** API session tokens, cached per address for this tab so a reload does not ask to sign again. */
const key = (address: string) => `zyrcle:token:${address.toLowerCase()}`;

/** The JWT's `exp` in ms (0 if unreadable). Not verified: the API is the judge, this only avoids reusing a stale token. */
export function expiresAt(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" ? payload.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

export function cachedToken(address: string, now = Date.now()): string | null {
  try {
    const token = sessionStorage.getItem(key(address));
    return token && expiresAt(token) - now > 60_000 ? token : null;
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
