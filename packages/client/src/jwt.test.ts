import { describe, expect, it } from "vitest";
import { accountOf, expiresAt, isFresh } from "./jwt";

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

describe("accountOf", () => {
  it("reads the resident's account from the token", () => {
    const addr = "0xfcb03fda4fd4079afa18fa5834d47fb73f03ce79";
    expect(accountOf(jwt({ addr, key: "0x70997970c51812dc3a010c7d01b50e0d17dc79c8" }))).toBe(addr);
  });

  it("returns null when the token has no account", () => {
    expect(accountOf(jwt({ sub: "x" }))).toBeNull();
    expect(accountOf(jwt({ addr: "not an address" }))).toBeNull();
    expect(accountOf("not-a-jwt")).toBeNull();
  });
});
