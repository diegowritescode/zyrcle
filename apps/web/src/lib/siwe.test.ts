import { describe, expect, it } from "vitest";
import { buildSiweMessage } from "./siwe";

// The same message is parsed by apps/api/tests/test_auth.py: if either side changes the format,
// one of the two tests fails.
const EXPECTED = [
  "zyrcle.test wants you to sign in with your Ethereum account:",
  "0x52908400098527886E0F7030069857D2E4169EE7",
  "",
  "Sign in to Zyrcle.",
  "",
  "URI: https://zyrcle.test",
  "Version: 1",
  "Chain ID: 20261121",
  "Nonce: abc123XYZ",
  "Issued At: 2026-11-22T15:30:00.123Z",
].join("\n");

describe("buildSiweMessage", () => {
  it("builds the exact EIP-4361 message the API verifies", () => {
    const message = buildSiweMessage({
      domain: "zyrcle.test",
      address: "0x52908400098527886E0F7030069857D2E4169EE7",
      chainId: 20261121,
      nonce: "abc123XYZ",
      issuedAt: new Date(Date.UTC(2026, 10, 22, 15, 30, 0, 123)),
    });
    expect(message).toBe(EXPECTED);
  });
});
