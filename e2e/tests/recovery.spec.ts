/**
 * A lost phone (ADR 0010): the old phone confirms a recovery email, a new phone recovers the
 * account, 48 hours pass on the chain, the account arrives with its balance, and the old phone is
 * locked out. Runs after the journey: it moves the chain's clock forward.
 */
import { expect, test, type Page } from "@playwright/test";
import { Errors, MOB, emailCode, overflow, rpc, sleep, sql } from "./helpers";

test.describe.configure({ mode: "serial" });

type Phone = { page: Page; session: { address: string; owner: string } | null };
const errors = new Errors();
const email = `diego-${Date.now().toString(36)}@example.com`;
let old: Phone;
let fresh: Phone;

async function newPhone(browser: import("@playwright/test").Browser, name: string): Promise<Phone> {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  const p: Phone = { page, session: null };
  errors.watch(page, name);
  page.on("dialog", (d) => d.accept());
  page.on("response", async (r) => {
    if (r.url().endsWith("/v1/auth/verify") && r.ok()) p.session = await r.json();
  });
  return p;
}

async function ready(p: Phone) {
  await p.page.goto(`${MOB}/`, { waitUntil: "networkidle" });
  await p.page.waitForFunction(
    () => [...document.querySelectorAll('[role="button"]')].some((b) => b.textContent?.includes("Reciclar ahora") && b.getAttribute("aria-disabled") !== "true"),
    null,
    { timeout: 30_000 },
  );
}

const recoveryStatus = async () => (await sql<{ status: string }>("select status from account_recovery order by created_at desc limit 1"))[0]?.status;
const balance = (page: Page) => page.locator('[aria-label^="Saldo "]').first().getAttribute("aria-label");

test.beforeAll(async ({ browser }) => {
  old = await newPhone(browser, "old phone");
  fresh = await newPhone(browser, "new phone");
});

test.afterEach(() => {
  expect(errors.list, "browser errors").toEqual([]);
});

test("the old phone holds a balance and protects it with a confirmed email", async () => {
  await ready(old);
  const { address, owner } = old.session!;
  await rpc("anvil_setBalance", [address, "0x" + (12_500n * 10n ** 18n).toString(16)]);
  await rpc("anvil_setBalance", [owner, "0x" + (3_000n * 10n ** 18n).toString(16)]);
  await ready(old); // a new sign-in moves the coins left on the key into the account
  await old.page.waitForFunction(() => {
    const label = document.querySelector('[aria-label^="Saldo "]')?.getAttribute("aria-label") ?? "";
    return Number(label.replace(/\D/g, "").slice(0, 5)) >= 15_499;
  }, null, { timeout: 30_000 });
  await expect(old.page.getByText("Protege tu saldo")).toBeVisible();

  await old.page.getByRole("button", { name: "Agregar correo" }).click();
  await expect(old.page.getByText("Correo de recuperación")).toBeVisible();
  await old.page.getByLabel("Correo").fill(email);
  await old.page.getByRole("button", { name: "Enviarme un código" }).click();
  await expect(old.page.getByText(/Te enviamos un código de 6 números a d•••@example\.com/)).toBeVisible();
  await old.page.getByLabel("Código").fill(await emailCode(email, 0));
  await old.page.getByRole("button", { name: "Confirmar correo" }).click();
  await expect(old.page.getByText(email)).toBeVisible();
  expect(await overflow(old.page)).toBe(0);
});

test("a new phone asks for the account and the old one is warned", async () => {
  await ready(fresh);
  await fresh.page.getByRole("tab", { name: /Cuenta/ }).click();
  await expect(fresh.page.getByText("¿Perdiste tu teléfono anterior?")).toBeVisible();
  await fresh.page.getByRole("button", { name: "Recuperar mi cuenta" }).click();
  await expect(fresh.page.getByText("Escribe el correo que confirmaste en tu teléfono anterior.")).toBeVisible();
  // The Cuenta tab stays mounted under the pushed screen: act on what is visible.
  await fresh.page.locator('input[aria-label="Correo"] >> visible=true').fill(email.toUpperCase());
  await fresh.page.locator('[role="button"]:has-text("Enviarme un código") >> visible=true').click();
  await fresh.page.locator('input[aria-label="Código"] >> visible=true').fill(await emailCode(email, 1));
  await fresh.page.locator('[role="button"]:has-text("Recuperar mi cuenta") >> visible=true').click();
  await expect(fresh.page.getByText(/Tu cuenta llega el/).filter({ visible: true }).first()).toBeVisible();
  expect(await overflow(fresh.page)).toBe(0);

  for (let i = 0; i < 80 && (await recoveryStatus()) !== "waiting"; i++) await sleep(250);
  expect(await recoveryStatus()).toBe("waiting");
  await old.page.reload({ waitUntil: "networkidle" });
  await expect(old.page.getByText("¿Estás cambiando de teléfono?")).toBeVisible();
  await expect(old.page.getByText(/Tu cuenta pasará a otro teléfono/)).toBeVisible();
});

test("48 hours later the account arrives on the new phone with its balance and the old one is locked out", async () => {
  await rpc("evm_increaseTime", [48 * 3600 + 60]);
  await rpc("evm_mine", []);
  await sql("update account_recovery set next_attempt_at = now() where status = 'waiting'");
  for (let i = 0; i < 120 && (await recoveryStatus()) !== "done"; i++) await sleep(250);
  expect(await recoveryStatus()).toBe("done");

  await fresh.page.reload({ waitUntil: "networkidle" });
  await expect(fresh.page.getByText("Recuperaste tu cuenta", { exact: true }).filter({ visible: true }).first()).toBeVisible();
  await fresh.page.locator('[role="button"]:has-text("Ir al inicio") >> visible=true').click();
  await expect(fresh.page.getByText("Recuperaste tu cuenta: tu saldo, tu historial y tus turnos ya están aquí.").filter({ visible: true }).first()).toBeVisible();
  await fresh.page.waitForFunction(() => (document.querySelector('[aria-label^="Saldo "]')?.getAttribute("aria-label") ?? "").startsWith("Saldo 15"), null, { timeout: 30_000 });
  expect(await balance(fresh.page)).toMatch(/^Saldo 15/);
  expect(fresh.session!.address).toBe(old.session!.address);

  await old.page.reload({ waitUntil: "networkidle" });
  await expect(old.page.getByText("Esta cuenta ya está en otro teléfono")).toBeVisible();
});
