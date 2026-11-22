import { describe, expect, it } from "vitest";
import { expiresAt } from "./token";

const jwt = (payload: object) =>
  ["e30", btoa(JSON.stringify(payload)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_"), "sig"].join(".");

describe("expiresAt", () => {
  it("reads the JWT expiry in milliseconds", () => {
    expect(expiresAt(jwt({ sub: "x", exp: 1_800_000_000 }))).toBe(1_800_000_000_000);
  });

  it("treats unreadable tokens as expired", () => {
    expect(expiresAt("not-a-jwt")).toBe(0);
    expect(expiresAt(jwt({ sub: "x" }))).toBe(0);
  });
});
