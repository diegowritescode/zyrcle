import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Browser, Page } from "@playwright/test";
import pg from "pg";

/** Where stack/up.sh left its state and logs. */
export const STATE = process.env.E2E_STATE ?? resolve(process.cwd(), ".stack");
export const API = "http://127.0.0.1:8010";
export const RPC = "http://127.0.0.1:8546";
export const WEB = "http://localhost:4180";
export const MOB = "http://localhost:8092";

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function apiEnv(): Record<string, string> {
  const lines = readFileSync(`${STATE}/api.env`, "utf8").split("\n").filter((l) => l.includes("="));
  return Object.fromEntries(lines.map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]));
}

/** Headers of the shared operator token (ADR 0014), for setting up what a step does not test. */
export const ops = () => ({ Authorization: `Bearer ${apiEnv().ZYRCLE_OPERATOR_TOKEN}`, "content-type": "application/json" });

export const rpc = (method: string, params: unknown[]) =>
  fetch(RPC, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) }).then((r) => r.json());

/** Browser errors, minus the 4xx answers that some steps cause on purpose. */
export class Errors {
  list: string[] = [];
  watch(page: Page, name: string) {
    page.on("console", (m) => {
      if (m.type() === "error" && !/status of (401|403|404|409|422)/.test(m.text())) this.list.push(`${name}: ${m.text()}`);
    });
    page.on("pageerror", (e) => this.list.push(`${name}: ${e}`));
  }
}

export async function openPage(browser: Browser, errors: Errors, name: string, mobile = false): Promise<Page> {
  const viewport = mobile ? { width: 390, height: 844 } : { width: 1280, height: 900 };
  const context = await browser.newContext({ viewport, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile });
  const page = await context.newPage();
  errors.watch(page, name);
  return page;
}

/** Horizontal overflow in pixels: 0 means the page fits its width. */
export const overflow = (p: Page) => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

/** Six-digit codes emailed to `address`, oldest first. The stack writes emails to the API log. */
function emailCodes(address: string): string[] {
  const log = readFileSync(`${STATE}/api.log`, "utf8");
  const marker = `email to ${address}:`;
  const codes: string[] = [];
  for (let at = log.indexOf(marker); at !== -1; at = log.indexOf(marker, at + marker.length)) {
    const code = log.slice(at + marker.length, at + marker.length + 400).match(/\b(\d{6})\b/)?.[1];
    if (code) codes.push(code);
  }
  return codes;
}

/** The newest code emailed to `address`, once more than `seen` have arrived. */
export async function emailCode(address: string, seen = 0): Promise<string> {
  for (let i = 0; i < 80; i++) {
    const codes = emailCodes(address);
    if (codes.length > seen) return codes[codes.length - 1];
    await sleep(250);
  }
  throw new Error(`no new code emailed to ${address}`);
}

/** One query against the stack's database, for what no screen shows (worker timing). */
export async function sql<T = Record<string, unknown>>(text: string): Promise<T[]> {
  const client = new pg.Client({ connectionString: `${process.env.E2E_PG ?? "postgresql://zyrcle:zyrcle@localhost:5432"}/zyrcle_e2e` });
  await client.connect();
  try {
    return (await client.query(text)).rows as T[];
  } finally {
    await client.end();
  }
}

/** A phone running the app: it creates its key and signs in on its own. */
export async function phone(browser: Browser, errors: Errors, name: string): Promise<{ page: Page; address: string }> {
  const page = await openPage(browser, errors, name, true);
  let address: string | null = null;
  page.on("response", async (r) => {
    if (r.url().endsWith("/v1/auth/verify") && r.ok()) address = (await r.json()).address;
  });
  await page.goto(`${MOB}/`, { waitUntil: "networkidle" });
  for (let i = 0; i < 80 && !address; i++) await sleep(250);
  if (!address) throw new Error(`${name} did not sign in`);
  return { page, address };
}
