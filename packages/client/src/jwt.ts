/** The JWT's payload, unverified (null if unreadable). The API is the judge; the apps only read it. */
function claims(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(part.padEnd(part.length + ((4 - (part.length % 4)) % 4), "=")));
  } catch {
    return null;
  }
}

/** The JWT's `exp` in ms (0 if unreadable): only to avoid reusing a token about to expire. */
export function expiresAt(token: string): number {
  const exp = claims(token)?.exp;
  return typeof exp === "number" ? exp * 1000 : 0;
}

/** True when the token is still good for at least `marginMs`. */
export function isFresh(token: string, now = Date.now(), marginMs = 60_000): boolean {
  return expiresAt(token) - now > marginMs;
}

/** The resident's account (where their ZYR lives) named in the token, or null. It differs from the
 * key that signed in once smart accounts are on (docs/adr/0010). */
export function accountOf(token: string): string | null {
  const addr = claims(token)?.addr;
  return typeof addr === "string" && /^0x[0-9a-fA-F]{40}$/.test(addr) ? addr : null;
}
