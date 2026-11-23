/**
 * The Safe that holds ZyrcleChain's admin powers (ADR 0040): Diego's three signers are a browser
 * wallet, his phone's wallet and a paper key. Here a stand-in wallet signs on the multisig page,
 * the paper key signs on the command line, and the proposal runs on the local chain.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { STATE, WEB } from "./helpers";

test.describe.configure({ mode: "serial" });

const ADMIN_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"; // anvil account 0
const owners = [generatePrivateKey(), generatePrivateKey(), generatePrivateKey()].map((k) => ({ key: k, account: privateKeyToAccount(k) }));
const work = mkdtempSync(join(tmpdir(), "zyrcle-safe-"));
const py = resolve(process.env.E2E_PY ?? resolve(process.cwd(), "../apps/api/.venv/bin"), "python");
const chainEnv = Object.fromEntries(
  readFileSync(`${STATE}/chain.env`, "utf8").split("\n").filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]),
);

function safeCli(args: string[], input?: string): string {
  return execFileSync(py, ["-m", "zyrcle_api.cli", "safe", ...args], {
    cwd: resolve(process.cwd(), "../apps/api"),
    env: { ...process.env, ZYRCLE_CHAIN_RPC_URL: "http://127.0.0.1:8546", ZYRCLE_TREASURY_ADDRESS: chainEnv.ZYRCLE_TREASURY_ADDRESS, ZYRCLE_ACCOUNT_FACTORY_ADDRESS: chainEnv.ZYRCLE_ACCOUNT_FACTORY_ADDRESS },
    input,
    encoding: "utf8",
  });
}

let safe = "";
const adminFile = join(work, "admin.pk");
const proposalFile = join(work, "proof.json");

test("the Safe is deployed with three owners and a threshold of two, and gets the powers", () => {
  writeFileSync(adminFile, ADMIN_KEY);
  const out = safeCli(["deploy", "--admin-key-file", adminFile, "--owners", owners.map((o) => o.account.address).join(","), "--threshold", "2"]);
  safe = /^SAFE=(0x[0-9a-fA-F]{40})$/m.exec(out)![1];
  safeCli(["grant", "--admin-key-file", adminFile, "--safe", safe]);
  safeCli(["propose", "--safe", safe, "--what", "proof", "--out", proposalFile]);
});

test("an owner signs on the multisig page with a wallet; a stranger cannot", async ({ browser }) => {
  for (const [who, expectOwner] of [[owners[0], true], [{ key: generatePrivateKey(), account: privateKeyToAccount(generatePrivateKey()) }, false]] as const) {
    const context = await browser.newContext();
    const page = await context.newPage();
    // A stand-in for MetaMask: the page talks to window.ethereum; signing happens on the test side.
    await page.exposeFunction("__signTypedData", async (json: string) => {
      const { types, domain, message, primaryType } = JSON.parse(json);
      const { EIP712Domain: _d, ...rest } = types;
      return who.account.signTypedData({ domain, types: rest, primaryType, message });
    });
    await page.addInitScript((address: string) => {
      (window as unknown as { ethereum: unknown }).ethereum = {
        // Like MetaMask: the app's wallet layer listens for account and chain changes.
        on: () => {},
        removeListener: () => {},
        request: async ({ method, params }: { method: string; params?: unknown[] }) => {
          if (method === "eth_requestAccounts" || method === "eth_accounts") return [address];
          if (method === "eth_chainId") return "0x" + (20261121).toString(16);
          if (method === "eth_signTypedData_v4") return (window as unknown as { __signTypedData: (j: string) => Promise<string> }).__signTypedData(params![1] as string);
          throw Object.assign(new Error(`unsupported ${method}`), { code: 4200 });
        },
      };
    }, who.account.address);
    await page.goto(`${WEB}/multisig`, { waitUntil: "networkidle" });
    await page.getByLabel("Archivo de la propuesta").setInputFiles(proposalFile);
    // The stranger opens the file the owner already signed.
    await expect(page.getByLabel("Firmas")).toContainText(expectOwner ? "0 de 2 firmas" : "1 de 2 firmas");
    await page.getByRole("button", { name: "Firmar con mi billetera" }).click();
    if (expectOwner) {
      await expect(page.getByLabel("Firmas")).toContainText("1 de 2 firmas");
      const download = page.waitForEvent("download");
      await page.getByRole("button", { name: "Descargar propuesta" }).click();
      await (await download).saveAs(proposalFile);
    } else {
      await expect(page.getByText(/no es dueña de este Safe/)).toBeVisible();
    }
    await context.close();
  }
});

test("the paper key signs on the command line, then anyone executes it", () => {
  expect(safeCli(["sign", "--proposal", proposalFile, "--key-file", "-"], owners[2].key)).toContain("2 of 2");
  expect(safeCli(["exec", "--proposal", proposalFile, "--key-file", adminFile])).toContain("executed");
  const admin = privateKeyToAccount(ADMIN_KEY).address;
  expect(safeCli(["status", "--safe", safe, "--admin", admin])).toMatch(/AccountFactory\s+llave admin: sí\s+Safe: sí/);
});
