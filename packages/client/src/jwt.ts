/**
 * The JWT's `exp` in ms (0 if unreadable). Not verified: the API is the judge; this only avoids
 * reusing a token that is about to expire.
 */
export function expiresAt(token: string): number {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(part.padEnd(part.length + ((4 - (part.length % 4)) % 4), "=")));
    return typeof payload.exp === "number" ? payload.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

/** True when the token is still good for at least `marginMs`. */
export function isFresh(token: string, now = Date.now(), marginMs = 60_000): boolean {
  return expiresAt(token) - now > marginMs;
}
