/**
 * What an error report may carry (docs/adr/0033): the same rules as the API's observability.py.
 * Email addresses, long hex strings (private keys, signatures), bearer tokens and JWTs are replaced;
 * request bodies, cookies, headers and the user are dropped. Account addresses (40 hex) stay: they
 * are public on the chain.
 */
export const REDACTED = "[redacted]";
const PATTERNS = [/bearer\s+[\w.~+/=-]+/gi, /\beyJ[\w-]+\.[\w-]+\.[\w-]+/g, /[\w.+-]+@[\w-]+\.[\w.-]+/g, /\b(?:0x)?[0-9a-fA-F]{64,}\b/g];

function clean(value: unknown): unknown {
  if (typeof value === "string") return PATTERNS.reduce((s, p) => s.replace(p, REDACTED), value);
  if (Array.isArray(value)) return value.map(clean);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, clean(v)]));
  return value;
}

/** A `beforeSend` for Sentry's browser and React Native SDKs. */
export function scrubReport<T extends object>(event: T): T {
  const e = { ...event } as Record<string, unknown>;
  if (e.request && typeof e.request === "object") {
    const { data: _data, cookies: _cookies, headers: _headers, ...rest } = e.request as Record<string, unknown>;
    e.request = { ...rest, ...("query_string" in rest ? { query_string: REDACTED } : {}) };
  }
  delete e.user;
  return clean(e) as T;
}
