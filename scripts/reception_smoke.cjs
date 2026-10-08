const { chromium } = require("playwright");
const { authenticate } = require("./smoke_auth.cjs");

const receptionUrl = "http://127.0.0.1:8000/recepcao/pre-consultas/";
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

  const response = await authenticate(page, receptionUrl);
  assert(response && response.status() === 200, "A tela da recepção não retornou 200.");
  assert(await page.locator("#reception-title").isVisible(), "O título operacional não está visível.");
  assert(await page.locator(".logout-button").isVisible(), "O botão Sair não está visível no desktop.");
  assert(await page.locator(".reception-row").count() === 6, "A lista inicial não exibiu seis registros.");
  assert((await page.locator("body").innerText()).includes("*****"), "Os telefones não estão mascarados.");
  await page.screenshot({ path: "artifacts/recepcao-desktop.png", fullPage: true });

  await page.locator(".reception-row").first().click();
  assert(await page.locator(".record-drawer").isVisible(), "O painel lateral de detalhes não abriu.");
  assert(await page.locator(".timeline-event").count() >= 2, "A linha do tempo operacional não foi renderizada.");
  const detailText = await page.locator(".record-drawer").innerText();
  assert(!detailText.includes("Visão geral") && !detailText.includes("Transcrição"), "O painel expôs conteúdo clínico.");
  await page.waitForTimeout(400);
  await page.screenshot({ path: "artifacts/recepcao-detalhe.png" });
  await page.locator(".record-drawer [data-close-drawer]").first().click();

  await page.locator(".js-open-form").click();
  assert(await page.locator(".form-drawer").isVisible(), "O formulário lateral não abriu.");
  assert(
    Boolean(await page.locator('.form-drawer input[name="scheduled_date"]').inputValue()),
    "A data demonstrativa inicial não foi preenchida.",
  );
  await page.waitForTimeout(400);
  await page.screenshot({ path: "artifacts/recepcao-formulario.png" });
  await page.locator('.reception-form button[type="submit"]').click();
  await page.waitForLoadState("networkidle");
  assert(await page.locator(".form-drawer").isVisible(), "O formulário com erro não permaneceu aberto.");
  assert(await page.locator(".field-error").count() >= 5, "Os erros de validação não apareceram junto aos campos.");

  await page.goto(receptionUrl, { waitUntil: "networkidle" });
  await page.locator('select[name="estado"]').selectOption("ready");
  await page.waitForURL("**estado=ready**");
  assert(await page.locator(".reception-row").count() === 1, "O filtro por estado não retornou o caso pronto.");
  assert(await page.locator('a[href*="/medico/pre-consultas/"]').count() === 0, "A recepção recebeu link para conteúdo clínico.");

  await page.goto(receptionUrl, { waitUntil: "networkidle" });
  await page.locator('input[name="q"]').fill("Paulo");
  await page.locator('input[name="q"]').press("Enter");
  await page.waitForURL("**q=Paulo**");
  assert(await page.locator(".reception-row").count() === 1, "A busca operacional não filtrou o paciente.");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(receptionUrl, { waitUntil: "networkidle" });
  const firstRow = await page.locator(".reception-row").first().boundingBox();
  assert(firstRow && firstRow.width <= 362, "A lista móvel ultrapassou a largura útil.");
  assert(await page.locator(".logout-button").isVisible(), "O botão Sair não está visível no mobile.");
  await page.locator(".js-open-form").click();
  await page.waitForTimeout(400);
  const mobileDrawer = await page.locator(".form-drawer").boundingBox();
  assert(
    mobileDrawer && mobileDrawer.width <= 390,
    `O formulário lateral não se adaptou ao celular: ${JSON.stringify(mobileDrawer)}`,
  );
  await page.locator(".form-drawer [data-close-drawer]").first().click();
  await page.screenshot({ path: "artifacts/recepcao-mobile.png", fullPage: true });

  assert(runtimeErrors.length === 0, `Erros no navegador: ${runtimeErrors.join(" | ")}`);
  console.log(JSON.stringify({
    status: response.status(),
    initialRows: 6,
    maskedPhones: true,
    recordDrawer: true,
    operationalTimeline: true,
    formDrawer: true,
    serverValidationErrors: true,
    statusFilter: true,
    patientSearch: true,
    noClinicalLink: true,
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
