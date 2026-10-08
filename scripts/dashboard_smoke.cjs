const { chromium } = require("playwright");
const { authenticate } = require("./smoke_auth.cjs");

const dashboardUrl = "http://127.0.0.1:8000/medico/painel/";
const detailPath = "/medico/pre-consultas/demo/";
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

  const response = await authenticate(page, dashboardUrl);
  assert(response && response.status() === 200, "O painel não retornou 200.");
  assert(await page.locator("#dashboard-title").isVisible(), "O título da agenda não está visível.");
  assert(await page.locator(".logout-button").isVisible(), "O botão Sair não está visível no desktop.");
  assert(await page.locator(".appointment-row").count() === 5, "A agenda de hoje não exibiu cinco casos.");
  assert(await page.locator('a[href="' + detailPath + '"]').count() === 1, "A ação da pré-consulta pronta não é única.");
  const indicatorValues = await page.locator(".indicator-strip article strong").allTextContents();
  assert(indicatorValues.join(",") === "5,1,1", "Os indicadores iniciais estão incoerentes.");
  await page.screenshot({ path: "artifacts/painel-medico-desktop.png", fullPage: true });

  await page.locator('a[href="' + detailPath + '"]').click();
  await page.waitForURL(`**${detailPath}`);
  assert(await page.locator("#summary-title").isVisible(), "O link não abriu a pré-consulta existente.");
  await page.locator(".eyebrow-link").click();
  await page.waitForURL("**/medico/painel/");
  assert(await page.locator("#dashboard-title").isVisible(), "O retorno ao painel não funcionou.");

  await page.locator('select[name="clinica"]').selectOption({ label: "Centro Médico Aurora — Unidade Itaim" });
  await page.waitForURL("**clinica=**");
  assert(await page.locator(".appointment-row").count() === 2, "O filtro de clínica não retornou dois casos.");
  const filteredIndicators = await page.locator(".indicator-strip article strong").allTextContents();
  assert(filteredIndicators.join(",") === "2,0,1", "Os indicadores não acompanharam o filtro de clínica.");

  await page.goto(dashboardUrl, { waitUntil: "networkidle" });
  await page.locator('input[name="q"]').fill("Rafael");
  await page.locator('input[name="q"]').press("Enter");
  await page.waitForURL("**q=Rafael**");
  assert(await page.locator(".appointment-row").count() === 1, "A busca por paciente não filtrou a agenda.");

  await page.goto(dashboardUrl, { waitUntil: "networkidle" });
  const originalDate = await page.locator('input[name="data"]').inputValue();
  await page.locator('[data-date-step="1"]').click();
  await page.waitForFunction((value) => new URL(location.href).searchParams.get("data") !== value, originalDate);
  assert(await page.locator('[data-consultation="demo-amanha"]').count() === 1, "O próximo dia não exibiu o caso esperado.");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(dashboardUrl, { waitUntil: "networkidle" });
  const firstRow = await page.locator(".appointment-row").first().boundingBox();
  assert(firstRow && firstRow.width <= 362, "A agenda móvel ultrapassou a largura útil.");
  assert(await page.locator(".logout-button").isVisible(), "O botão Sair não está visível no mobile.");
  await page.screenshot({ path: "artifacts/painel-medico-mobile.png", fullPage: true });

  assert(runtimeErrors.length === 0, `Erros no navegador: ${runtimeErrors.join(" | ")}`);
  console.log(JSON.stringify({
    status: response.status(),
    title: await page.title(),
    desktopRows: 5,
    indicators: indicatorValues,
    readyLinkToExistingDetail: true,
    backToDashboard: true,
    clinicFilter: true,
    patientSearch: true,
    dateSelection: true,
    mobileLayout: true,
    logoutButton: true,
    runtimeErrors,
  }, null, 2));
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
}).finally(async () => {
  if (activeBrowser) await activeBrowser.close();
});

