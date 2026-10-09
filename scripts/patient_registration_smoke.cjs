const { chromium } = require("playwright");
const { authenticate } = require("./smoke_auth.cjs");
let browser;
const assert = (condition, message) => { if (!condition) throw new Error(message); };

(async () => {
  browser = await chromium.launch({
    executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const url = (process.env.SMOKE_BASE_URL || "http://127.0.0.1:8001") + "/recepcao/pre-consultas/";
  await authenticate(page, url);
  await page.locator(".js-open-form").click();
  await page.locator('[name="patient_name"]').fill(process.env.SMOKE_PATIENT_NAME);
  await page.locator('[name="phone"]').fill(process.env.SMOKE_PATIENT_PHONE);
  await page.locator('[name="doctor"]').selectOption(process.env.SMOKE_DOCTOR_ID);
  await page.locator('[name="clinic"]').selectOption(process.env.SMOKE_CLINIC_ID);
  await page.locator('[name="appointment_type"]').fill("Consulta fictícia smoke");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator('.reception-form button[type="submit"]').click(),
  ]);
  const choice = page.locator('select[name="patient_choice"]');
  assert(await choice.isVisible(), "Escolha explícita não apareceu.");
  assert(await choice.inputValue() === "", "Paciente selecionado automaticamente.");
  assert(await choice.locator(`option[value="${process.env.SMOKE_PATIENT_ID}"]`).count() === 1,
    "Paciente autorizado não apareceu.");
  assert(await choice.locator('option[value="new"]').count() === 1, "Opção novo ausente.");
  assert(await page.locator('.reception-field--patient_choice .field-error').count() === 1,
    "Confirmação não foi exigida pelo servidor.");
  await page.screenshot({ path: "artifacts/patient-choice-desktop.png", fullPage: true });
  await choice.selectOption(process.env.SMOKE_PATIENT_ID);
  await choice.selectOption("new");
  // Do not finalize either selection: preserve the local validation database.
  await page.setViewportSize({ width: 390, height: 844 });
  const box = await choice.boundingBox();
  assert(box && box.width <= 350, "Escolha ultrapassa a largura móvel.");
  await page.screenshot({ path: "artifacts/patient-choice-mobile.png", fullPage: true });
  assert(errors.length === 0, "Erros de execução no navegador.");
  console.log(JSON.stringify({ explicitChoice: true, authorizedCandidate: true,
    newOption: true, desktopAndMobile: true, noRegistrationWritten: true }));
})().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
}).finally(async () => { if (browser) await browser.close(); });
