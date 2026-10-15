const { chromium } = require("playwright");
const { authenticate } = require("./smoke_auth.cjs");
const base = process.env.SMOKE_BASE_URL;
const slug = process.env.SMOKE_CASE_SLUG;
let browser;
function assert(value, message) { if (!value) throw new Error(message); }

(async () => {
  browser = await chromium.launch({ executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await authenticate(page, base + "/medico/painel/");
  const row = page.locator(`[data-consultation="${slug}"]`);
  const button = row.getByRole("button", { name: "Publicar síntese simulada" });
  assert(await button.isVisible(), "Publicação não disponível no painel autorizado.");
  assert(await page.locator(".summary-item").count() === 0, "Conteúdo foi exposto antes da publicação.");
  const unavailable = await page.request.get(base + `/medico/pre-consultas/${slug}/`);
  assert(unavailable.status() === 403, "Completed foi liberada antes da publicação.");
  await page.screenshot({ path: "artifacts/publicacao-pendente-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  assert(await button.isVisible(), "Ação de publicação não visível no mobile.");
  assert(await page.locator(".logout-button").isVisible(), "Saída não visível no mobile.");
  await page.screenshot({ path: "artifacts/publicacao-pendente-mobile.png", fullPage: true });
  await button.click();
  await page.waitForURL(`**/medico/pre-consultas/${slug}/`);
  assert(await page.locator(".publication-notice").isVisible(), "Publicação simulada não foi identificada.");
  assert(await page.locator(".summary-item").count() > 0, "Resumo publicado não foi disponibilizado.");
  const summary = await page.locator(".summary-panel").boundingBox();
  const context = await page.locator(".context-panel").boundingBox();
  assert(summary.y < context.y, "Resumo não aparece antes das fontes no mobile.");
  await page.screenshot({ path: "artifacts/publicacao-pronta-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator(".js-view-source").first().click();
  assert(await page.locator("[data-source-item].is-highlighted").count() > 0, "Origem publicada não destacou a fonte.");
  await page.locator(".js-open-correction").first().click();
  await page.locator('.correction-form [name="new_value"]').fill("Ajuste exclusivamente fictício do smoke.");
  const correction = page.waitForResponse(res => res.url().endsWith("/correcoes/") && res.request().method() === "POST");
  await page.locator('.correction-form button[type="submit"]').click();
  assert((await correction).status() === 200, "Correção publicada não foi persistida.");
  await page.reload({ waitUntil: "networkidle" });
  assert((await page.locator(".summary-item__value").first().innerText()).includes("Ajuste exclusivamente fictício"), "Correção não aparece na apresentação.");
  const feedback = page.waitForResponse(res => res.url().endsWith("/feedback/") && res.request().method() === "POST");
  await page.locator('.js-feedback[data-kind="useful"]').first().click();
  assert((await feedback).status() === 200, "Feedback não foi persistido.");
  await page.locator('.note-card textarea[name="text"]').fill("Apontamento exclusivamente fictício do smoke.");
  const note = page.waitForResponse(res => res.url().endsWith("/apontamentos/") && res.request().method() === "POST");
  await page.locator('.note-card button[type="submit"]').click();
  assert((await note).status() === 200, "Apontamento não foi persistido.");
  await page.screenshot({ path: "artifacts/publicacao-pronta-desktop.png", fullPage: true });
  assert(errors.length === 0, "Erros JavaScript no fluxo de publicação.");
  console.log(JSON.stringify({ completedBlocked: true, explicitPublication: true, simulationIdentified: true,
    sourceReference: true, correctionPersisted: true, feedbackPersisted: true, notePersisted: true, desktopMobile: true }, null, 2));
})().catch(error => { console.error(error.message); process.exitCode = 1; })
  .finally(async () => { if (browser) await browser.close(); });
