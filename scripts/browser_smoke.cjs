const { chromium } = require("playwright");
const { authenticate } = require("./smoke_auth.cjs");

const url = "http://127.0.0.1:8000/medico/pre-consultas/demo/";
const browserPath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
let activeBrowser;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

(async () => {
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  activeBrowser = browser;
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const runtimeErrors = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") runtimeErrors.push(message.text());
  });

  const response = await authenticate(page, url);
  assert(response && response.status() === 200, "A página principal não retornou 200.");
  assert(await page.locator("#summary-title").isVisible(), "O resumo não está visível.");
  assert(await page.locator(".context-panel").isVisible(), "O painel de fontes não está visível.");
  assert(await page.locator(".logout-button").isVisible(), "O botão Sair não está visível no desktop.");

  const sourceButton = page.locator(".js-view-source").first();
  const sourceKey = await sourceButton.getAttribute("data-source");
  await sourceButton.click();
  assert(
    await page.locator(`[data-source-item="${sourceKey}"]`).evaluate((el) => el.classList.contains("is-highlighted")),
    "Ver origem não destacou a mensagem vinculada.",
  );

  await page.locator('[data-tab="attachments"]').click();
  assert(await page.locator("#panel-attachments").isVisible(), "A aba Anexos não abriu.");
  await page.locator("#panel-attachments .js-open-attachment").first().click();
  await page.locator(".viewer-empty").waitFor({ state: "visible" });
  assert(
    (await page.locator(".viewer-message").innerText()).includes("ainda não fornecido"),
    "O visualizador não mostrou o estado amigável de arquivo ausente.",
  );
  await page.locator(".attachment-drawer .drawer-close").click();

  await page.locator(".js-open-correction").first().click();
  assert(await page.locator(".correction-dialog").isVisible(), "O diálogo de correção não abriu.");
  assert((await page.locator('.correction-form [name="new_value"]').inputValue()).length > 10, "O valor anterior não foi carregado para correção.");
  await page.locator(".dialog-cancel").click();

  const feedbackResponse = page.waitForResponse((res) => res.url().endsWith("/feedback/") && res.request().method() === "POST");
  await page.locator('.js-feedback[data-kind="useful"]').click();
  assert((await feedbackResponse).status() === 200, "O feedback não foi salvo via POST.");
  await page.locator(".toast").waitFor({ state: "visible" });

  await page.screenshot({ path: "artifacts/preconsulta-desktop.png", fullPage: true });
  const desktopColumns = await page.locator(".workspace").evaluate((el) => getComputedStyle(el).gridTemplateColumns);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  const summaryBox = await page.locator(".summary-panel").boundingBox();
  const contextBox = await page.locator(".context-panel").boundingBox();
  assert(summaryBox && contextBox && summaryBox.y < contextBox.y, "No mobile, o resumo não aparece antes das fontes.");
  assert(await page.locator(".logout-button").isVisible(), "O botão Sair não está visível no mobile.");
  await page.screenshot({ path: "artifacts/preconsulta-mobile.png", fullPage: true });

  assert(runtimeErrors.length === 0, `Erros no navegador: ${runtimeErrors.join(" | ")}`);
  console.log(JSON.stringify({
    status: response.status(),
    title: await page.title(),
    sourceHighlight: true,
    attachmentMissingState: true,
    correctionDialog: true,
    feedbackPost: true,
    logoutButton: true,
    desktopColumns,
    mobileSummaryFirst: true,
    runtimeErrors,
  }, null, 2));
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
}).finally(async () => {
  if (activeBrowser) await activeBrowser.close();
});
