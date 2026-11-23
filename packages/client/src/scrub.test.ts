import { describe, expect, it } from "vitest";
import { REDACTED, scrubReport } from "./scrub";

describe("error reports", () => {
  it("lose emails, keys, tokens, bodies and the user, and keep account addresses", () => {
    const account = "0x" + "12".repeat(20);
    const out = scrubReport({
      message: `pago a ${account} falló para diego@example.com, firma 0x${"ab".repeat(65)}`,
      request: { url: "https://x/v1/me", data: "{}", headers: { Authorization: "Bearer a.b.c" }, cookies: "s=1", query_string: "e=diego@example.com" },
      user: { email: "diego@example.com" },
      breadcrumbs: [{ message: "token eyJhbGciOi.eyJzdWIiOi.c2ln" }],
    });
    expect(out.message).toBe(`pago a ${account} falló para ${REDACTED}, firma ${REDACTED}`);
    expect(out.request).toEqual({ url: "https://x/v1/me", query_string: REDACTED });
    expect("user" in out).toBe(false);
    expect(out.breadcrumbs).toEqual([{ message: `token ${REDACTED}` }]);
  });
});
