/**
 * A day on campus, every party in a real browser (ADR 0031): a university with two campuses, a
 * participant recycling, an operator in the console, a collector emptying a container from the
 * phone, the sale settled on chain, an impact certificate verified against the chain and its IPFS
 * copy, and a campus merchant paid from a phone who then redeems ZYR for pesos.
 *
 * The steps build on each other and run in order.
 */
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { API, Errors, MOB, SERVICES, WEB, emailCode, openPage, ops, overflow, phone, rpc, sleep } from "./helpers";

const PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

test.describe.configure({ mode: "serial" });

const errors = new Errors();
let desk: Page;
let collector: { page: Page; address: string };
const operatorEmail = `diego-${Date.now().toString(36)}@zyrcle.test`;

test.beforeAll(async ({ browser }) => {
  desk = await openPage(browser, errors, "desk");
  // The first admin, added with the shared token.
  const r = await fetch(`${API}/v1/operator/operators`, { method: "POST", headers: ops(), body: JSON.stringify({ email: operatorEmail, name: "Diego", role: "admin" }) });
  expect(r.status).toBe(201);
});

const todayDMY = () => {
  const [y, m, d] = new Date().toLocaleDateString("en-CA").split("-");
  return `${d}/${m}/${y}`;
};

async function uploadStatement(csv: string) {
  await desk.getByLabel("Extracto del banco").setInputFiles({ name: "extracto.csv", mimeType: "text/csv", buffer: Buffer.from(csv, "latin1") });
  await expect(desk.getByText(/movimientos: 1 nuevos/)).toBeVisible();
}

test.afterEach(() => {
  expect(errors.list, "browser errors").toEqual([]);
});

test("the university's dashboard shows its campuses and their containers", async () => {
  await desk.goto(`${WEB}/sites`, { waitUntil: "networkidle" });
  await expect(desk.getByText("Universidad Demo Zyrcle").first()).toBeVisible();
  await expect(desk.getByRole("button", { name: "Todas las sedes" })).toBeVisible();
  await desk.getByRole("group", { name: "Sede" }).getByRole("button", { name: "Campus Norte" }).click();
  await expect(desk.getByText("Contenedores inteligentes")).toBeVisible();
});

test("a participant recycles PET twice on the web and is paid an advance each time", async () => {
  await desk.goto(`${WEB}/recycling`, { waitUntil: "networkidle" });
  await expect(desk.getByText("sesión iniciada con tu firma")).toBeVisible({ timeout: 30_000 });
  for (const bottles of [6, 4]) {
    const card = desk
      .locator("div.rounded-xl", { hasText: "Contenedor PET y HDPE" })
      .filter({ has: desk.getByRole("button", { name: "Usar este contenedor" }) })
      .last();
    await card.locator("img").first().waitFor();
    await card.getByRole("button", { name: "Usar este contenedor" }).click();
    await desk.getByRole("button", { name: "Abrir contenedor" }).click();
    await expect(desk.getByText("Tapa abierta en").first()).toBeVisible();
    for (let i = 0; i < bottles; i++) await desk.getByRole("button", { name: /Botella PET/ }).click();
    await expect(desk.getByText("Recibiendo material").first()).toBeVisible();
    await sleep(1_200);
    await desk.getByRole("button", { name: "Terminé" }).click();
    await expect(desk.getByText("pagado en la cadena")).toBeVisible({ timeout: 60_000 });
    await desk.getByRole("button", { name: /Reciclar otra vez|Volver|Otro depósito/ }).first().click().catch(() => desk.reload({ waitUntil: "networkidle" }));
    await sleep(500);
  }
});

test("an operator signs in to the console with an emailed code", async ({ browser }) => {
  collector = await phone(browser, errors, "collector");
  await desk.goto(`${WEB}/console`, { waitUntil: "networkidle" });
  await desk.getByLabel("Correo").fill(operatorEmail);
  await desk.getByRole("button", { name: "Enviarme un código" }).click();
  await expect(desk.getByText(/le llegó un código/)).toBeVisible();
  await desk.getByRole("textbox", { name: "Código" }).fill(await emailCode(operatorEmail));
  await desk.getByRole("button", { name: "Entrar" }).click();
  await expect(desk.getByRole("heading", { name: "Pendientes" })).toBeVisible();
  await expect(desk.getByRole("heading", { name: "Tesorería" })).toBeVisible();
});

test("the operator names a collector and prints bag labels", async () => {
  await desk.getByRole("tab", { name: "Recolección" }).click();
  await desk.getByLabel("Dirección de su cuenta").fill(collector.address);
  await desk.getByLabel("Nombre").first().fill("Rosa Recicladora");
  await desk.getByRole("button", { name: "Nombrar" }).click();
  await expect(desk.getByText("Rosa Recicladora").first()).toBeVisible();
  await desk.getByLabel("Cuántas").fill("4");
  await desk.getByRole("button", { name: "Crear etiquetas" }).click();
  await expect(desk.getByText("4 etiquetas nuevas")).toBeVisible();
});

test("the operator records the collection center, its PET price, and the campus that sells to it", async () => {
  await desk.getByRole("tab", { name: "Precios" }).click();
  await desk.getByLabel("Nombre del centro").fill("Centro de acopio La 80");
  await desk.getByLabel("NIT").fill("900555111-2");
  await desk.getByRole("button", { name: "Agregar centro" }).click();
  await expect(desk.getByText("NIT 900555111-2")).toBeVisible();
  await desk.getByLabel("Precio de pet en Centro de acopio La 80").fill("1800");
  await desk.getByRole("row", { name: /PET/ }).filter({ has: desk.getByLabel("Precio de pet en Centro de acopio La 80") }).getByRole("button", { name: "Guardar" }).click();
  await expect(desk.getByText(/Centro de acopio La 80, .*1\.800 por kilo/)).toBeVisible();
  await desk.getByRole("combobox", { name: "Agregar una sede a Centro de acopio La 80" }).click();
  await desk.getByRole("option", { name: /Campus Norte/ }).click();
  await expect(desk.getByRole("button", { name: "Quitar Campus Norte" })).toBeVisible();
});

test("the collector empties the container into a sealed bag and every gram is accounted for", async () => {
  const p = collector.page;
  await p.reload({ waitUntil: "networkidle" });
  await p.getByRole("tab", { name: /Cuenta/ }).click();
  await p.getByRole("button", { name: "Abrir recolección" }).click();
  await expect(p.getByText("Vaciar un contenedor")).toBeVisible();
  const row = p.locator("div", { hasText: "Contenedor PET y HDPE" }).filter({ has: p.getByRole("button", { name: "Usar" }) }).last();
  await row.getByRole("button", { name: "Usar" }).click();
  await expect(p.getByText("Abierto", { exact: true })).toBeVisible();
  await p.getByRole("button", { name: "Escanear una bolsa" }).click();
  await p.getByRole("button", { name: /^PET · / }).first().click();
  await expect(p.getByText(/Saca solo el PET/)).toBeVisible();
  const before = await p.getByLabel(/^Peso /).getAttribute("aria-label");
  await p.getByRole("button", { name: "Demo: sacar el PET" }).click();
  await p.waitForFunction((b) => document.querySelector('[aria-label^="Peso "]')?.getAttribute("aria-label") !== b, before);
  await sleep(1_200);
  await p.getByRole("button", { name: "Listo" }).click();
  await p.getByRole("button", { name: "Sacar residuo" }).click();
  await p.getByRole("button", { name: "Demo: sacar todo lo demás" }).click();
  await sleep(1_500);
  await p.getByRole("button", { name: "Listo" }).click();
  await p.getByRole("button", { name: "Terminar y cerrar" }).click();
  // A fresh container held only these deposits, so both mass balances must close.
  await expect(p.getByText("Cuadra: todo lo que salió quedó pesado")).toBeVisible();
  await p.getByRole("button", { name: "Cerrar", exact: true }).first().click();
  await expect(p.getByText("Cerrada", { exact: true }).first()).toBeVisible();
  expect(await overflow(p)).toBe(0);
});

test("a sale confirmed against the bank settles the participants, the collector and the host on chain", async () => {
  await desk.getByRole("tab", { name: "Sedes" }).click();
  const hostAddress = "0x" + [...crypto.getRandomValues(new Uint8Array(20))].map((b) => b.toString(16).padStart(2, "0")).join("");
  await desk.getByLabel("Dirección de pago (ZyrcleChain)").first().fill(hostAddress);
  await desk.getByRole("button", { name: "Guardar" }).first().click();
  await sleep(800);
  await desk.getByRole("tab", { name: "Ventas" }).click();
  // The center's ticket, read from a photo (ADR 0038). The model is a stand-in that answers what the
  // test sets, so the test can check what the API sent it and what the console did with the answer.
  const sealed = await (await fetch(`${API}/v1/operator/bags?status=sealed`, { headers: ops() })).json();
  const bag = sealed[0];
  const kg = bag.grams / 1000;
  await fetch(`${SERVICES}/control/ticket-reading`, {
    method: "POST",
    body: JSON.stringify({
      readable: true,
      center_name: "Centro de acopio La 80",
      ticket_ref: "T-0001",
      date: new Date().toLocaleDateString("en-CA"),
      lines: [{ material: "pet", label: "PET botella", kg, cop_per_kg: Math.round(20_000 / kg), amount_cop: 20_000 }],
      total_cop: 20_000,
      notes: "",
    }),
  });
  await desk.getByLabel("Foto del tiquete").setInputFiles({ name: "tiquete.png", mimeType: "image/png", buffer: Buffer.from(PNG_1X1, "base64") });
  await desk.getByRole("button", { name: "Leer tiquete" }).click();
  await expect(desk.getByRole("cell", { name: bag.code, exact: true })).toBeVisible();
  expect(await (await fetch(`${SERVICES}/control/last-message`)).json()).toMatchObject({
    model: "claude-opus-5-5",
    fallbacks: "default",
    format: "json_schema",
  });
  await desk.getByRole("button", { name: "Usar en la venta" }).click();
  await expect(desk.locator("#sale-buyer")).toHaveValue("Centro de acopio La 80");
  await expect(desk.getByLabel("Número del tiquete")).toHaveValue("T-0001");
  await expect(desk.getByLabel("Pago por la bolsa").first()).toHaveValue("20000");
  await desk.getByRole("button", { name: "Registrar venta" }).click();
  await expect(desk.getByText("Por confirmar").first()).toBeVisible();
  // The bank match from the statement the operator downloads from the bank (ADR 0039).
  await uploadStatement(`Fecha;Descripción;Documento;Débito;Crédito\n${todayDMY()};TRANSF CENTRO LA 80 T-0001;8812;;20.000,00\n`);
  await desk.getByRole("row", { name: /Venta T-0001/ }).getByRole("button", { name: "Confirmar" }).click();
  await expect(desk.getByText(/· Liquidada/).first()).toBeVisible({ timeout: 60_000 });
  await desk.getByRole("button", { name: "Reparto" }).first().click();
  await expect(desk.getByText("Le toca")).toBeVisible();
  const split = await desk.locator("table").last().innerText();
  for (const party of ["Recolector", "Depósito", "Anfitrión"]) expect(split).toContain(party);
  const sales = await (await fetch(`${API}/v1/operator/sales`, { headers: ops() })).json();
  expect(sales[0].center_id).toBeTruthy(); // the sale names the center on record
});

test("the participant follows a deposit to the sale and sees their impact; the collector sees what to empty and what they earned", async () => {
  // ADR 0041: every step of the deposit, from the lid to the settlement, and the personal impact.
  await desk.goto(`${WEB}/recycling`, { waitUntil: "networkidle" });
  await expect(desk.getByText("sesión iniciada con tu firma")).toBeVisible({ timeout: 30_000 });
  await desk.getByRole("tab", { name: "Mis depósitos" }).click();
  await expect(desk.getByText("Mi impacto")).toBeVisible();
  await expect(desk.getByRole("term").filter({ hasText: "CO2e evitado" })).toBeVisible();
  await desk.getByRole("button", { name: /^Recorrido de PET/ }).first().click();
  const steps = desk.getByRole("list", { name: "Recorrido del depósito" });
  await expect(steps.getByText("Recogido", { exact: true })).toBeVisible();
  await expect(steps.getByText("A Centro de acopio La 80")).toBeVisible();
  await expect(steps.getByText(/^(Pagado|Liquidado)$/)).toBeVisible();
  // Leave once the QR reader's WebAssembly has arrived: navigating away mid-download logs an error.
  await desk
    .waitForFunction(() => performance.getEntriesByType("resource").some((e) => e.name.includes("zxing_reader")), undefined, { timeout: 10_000 })
    .catch(() => undefined);

  // ADR 0042: the collector's containers, fullest first, and what the sold bag paid them.
  const p = collector.page;
  await p.goto(`${MOB}/collect`, { waitUntil: "networkidle" });
  await expect(p.getByText("Qué vaciar primero")).toBeVisible();
  await expect(p.getByText("Lo que has ganado")).toBeVisible();
  expect(await overflow(p)).toBe(0);
});

test("the console fits a phone screen", async () => {
  await desk.setViewportSize({ width: 390, height: 844 });
  await desk.goto(`${WEB}/console`, { waitUntil: "networkidle" });
  await expect(desk.getByRole("heading", { name: "Pendientes" })).toBeVisible();
  expect(await overflow(desk)).toBe(0);
  await desk.setViewportSize({ width: 1280, height: 900 });
});

test("the host's dashboard draws the activity after the sale", async () => {
  await desk.goto(`${WEB}/sites`, { waitUntil: "networkidle" });
  await expect(desk.getByText("Actividad de reciclaje")).toBeVisible();
  await sleep(2_500); // the charts animate in
  const areas = await desk.locator(".recharts-area-area").evaluateAll((els) => els.map((e) => (e.getAttribute("d") || "").length));
  expect(areas.length).toBeGreaterThan(0);
  expect(Math.min(...areas)).toBeGreaterThan(0);
});

test("the console shows the system's health", async () => {
  await desk.goto(`${WEB}/console`, { waitUntil: "networkidle" });
  await expect(desk.getByRole("heading", { name: "Estado del sistema" })).toBeVisible();
});

test("an impact certificate is anchored with its IPFS copy and anyone can verify both", async () => {
  test.setTimeout(240_000);
  await desk.getByRole("tab", { name: "Certificados" }).click();
  await desk.getByRole("combobox").first().click();
  await desk.getByRole("option", { name: "Universidad Demo Zyrcle" }).click();
  await desk.getByLabel("Mes").fill(new Date().toLocaleDateString("en-CA").slice(0, 7));
  await desk.getByRole("button", { name: "Ver qué entra" }).click();
  await desk.getByRole("button", { name: "Emitir certificado" }).click();
  await expect(desk.getByText("Anclado").first()).toBeVisible({ timeout: 60_000 });

  const certificates = await (await fetch(`${API}/v1/operator/certificates`, { headers: ops() })).json();
  expect(certificates[0].ipfs_cid).toBeTruthy();
  await desk.goto(`${WEB}/certificates/${certificates[0].id}`, { waitUntil: "networkidle" });
  await desk.getByRole("button", { name: "Verificar" }).click();
  await expect(desk.getByText(/Coincide\..*la copia permanente en IPFS da la misma raíz/)).toBeVisible();
  await expect(desk.getByRole("link", { name: /Copia permanente en IPFS/ })).toHaveAttribute("href", new RegExp(`${certificates[0].ipfs_cid}$`));

  await desk.goto(`${WEB}/sites`, { waitUntil: "networkidle" });
  await expect(desk.getByText("Certificados de impacto")).toBeVisible();
  await expect(desk.getByRole("link", { name: "Ver y verificar" }).first()).toBeVisible();
});

test("a campus merchant charges with a QR, a participant pays from the phone, and the merchant redeems for pesos", async ({ browser }) => {
  test.setTimeout(240_000);
  const shop = await phone(browser, errors, "shop");
  const customer = await phone(browser, errors, "customer");
  await customer.page.getByRole("button", { name: "Acepto" }).click();
  await expect(customer.page.getByRole("button", { name: "Acepto" })).toHaveCount(0);
  await rpc("anvil_setBalance", [customer.address, "0x" + (5_000n * 10n ** 18n).toString(16)]);

  await desk.goto(`${WEB}/console`, { waitUntil: "networkidle" });
  await desk.getByRole("tab", { name: "Comercios" }).click();
  await desk.getByLabel("Dirección de su cuenta").fill(shop.address);
  await desk.getByLabel("Nombre del negocio").fill("Cafetería Central");
  await desk.getByLabel("NIT").fill("900123456-7");
  // Where participants find it (ADR 0041).
  await desk.getByRole("combobox", { name: "Campus" }).click();
  await desk.getByRole("option", { name: "Universidad Demo Zyrcle" }).click();
  await desk.getByRole("combobox", { name: "Sede del comercio" }).click();
  await desk.getByRole("option", { name: "Campus Norte" }).click();
  await desk.getByLabel("Dónde queda").fill("Bloque 7, primer piso");
  await desk.getByLabel("Horario").fill("L-V 7:00 a 18:00");
  await desk.getByLabel("Qué vende").fill("Café y almuerzos");
  await desk.getByRole("button", { name: "Agregar" }).click();
  await expect(desk.getByRole("cell", { name: "Cafetería Central" }).first()).toBeVisible();

  await shop.page.reload({ waitUntil: "networkidle" });
  await shop.page.getByRole("tab", { name: /Cuenta/ }).click();
  await shop.page.getByRole("button", { name: "Abrir comercio" }).click();
  await shop.page.getByLabel("Valor del cobro").fill("2500");
  await shop.page.getByLabel("Concepto").fill("Almuerzo");
  const created = shop.page.waitForResponse((r) => r.url().endsWith("/v1/merchant/charges") && r.request().method() === "POST");
  await shop.page.getByRole("button", { name: "Generar QR" }).click();
  const charge = await (await created).json();
  await expect(shop.page.getByLabel("Código QR del cobro")).toBeVisible();

  // What the QR carries is zyrcle://p/<id>; the scanner routes it to /pay?id=.
  await customer.page.goto(`${MOB}/pay?id=${charge.id}`, { waitUntil: "networkidle" });
  await customer.page.getByRole("button", { name: /Pagar/ }).click();
  await expect(customer.page.getByText("Pagado.")).toBeVisible({ timeout: 60_000 });
  await expect(shop.page.getByText(/Recibiste/)).toBeVisible();
  expect(await overflow(customer.page)).toBe(0);

  await shop.page.getByLabel("Valor a cambiar").fill("2000");
  await shop.page.getByRole("button", { name: "Solicitar el cambio" }).click();
  await expect(shop.page.getByText("Esperando la transferencia")).toBeVisible({ timeout: 60_000 });
  await desk.reload({ waitUntil: "networkidle" });
  await desk.getByRole("tab", { name: "Ventas" }).click();
  await uploadStatement(`Fecha;Descripción;Documento;Débito;Crédito\n${todayDMY()};PAGO CAFETERIA CENTRAL;9921;2.000,00;\n`);
  await desk.getByRole("row", { name: /Cambio a pesos · Cafetería Central/ }).getByRole("button", { name: "Confirmar" }).click();
  await desk.getByRole("tab", { name: "Comercios" }).click();
  await expect(desk.getByText("Pagado", { exact: true }).first()).toBeVisible();
  await expect(shop.page.getByText("Pagado en pesos")).toBeVisible();
  expect(await overflow(shop.page)).toBe(0);

  // The bookkeeping export, from the app and from the console (ADR 0045).
  const fromApp = shop.page.waitForEvent("download");
  await shop.page.getByRole("button", { name: "Descargar en Excel" }).click();
  expect((await fromApp).suggestedFilename()).toMatch(/^zyrcle-cafeteria-central-\d{4}-\d{2}-01-a-\d{4}-\d{2}-\d{2}\.xlsx$/);
  const fromConsole = desk.waitForEvent("download");
  await desk.getByRole("button", { name: "Exportar en CSV: Cafetería Central" }).click();
  const csv = await readFile((await (await fromConsole).path())!, "utf8");
  expect(csv).toMatch(/,Cobro,pagado,2500,Almuerzo,/);
  expect(csv).toMatch(/,Canje,transferido,2000,Canje de ZYR por pesos,/);
  expect(csv).toContain(",Cafetería Central,900123456-7");

  // Participants find it in "Dónde gastar", on the phone and on the web (ADR 0041).
  await customer.page.goto(`${MOB}/spend`, { waitUntil: "networkidle" });
  await expect(customer.page.getByText("Cafetería Central")).toBeVisible();
  await expect(customer.page.getByText("Bloque 7, primer piso")).toBeVisible();
  expect(await overflow(customer.page)).toBe(0);
  await desk.goto(`${WEB}/recycling`, { waitUntil: "networkidle" });
  await desk.getByRole("tab", { name: "Dónde gastar" }).click();
  const listing = desk.getByRole("region", { name: "Universidad Demo Zyrcle · Campus Norte" });
  await expect(listing.getByText("Cafetería Central")).toBeVisible();
  await expect(listing.getByText("L-V 7:00 a 18:00")).toBeVisible();
});
