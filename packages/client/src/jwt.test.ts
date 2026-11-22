import { describe, expect, it } from "vitest";
import { expiresAt, isFresh } from "./jwt";

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

describe("isFresh", () => {
  it("rejects tokens about to expire", () => {
    const token = jwt({ exp: 1_000 });
    expect(isFresh(token, 900_000)).toBe(true);
    expect(isFresh(token, 950_000)).toBe(false);
  });
});
