const { chromium } = require("playwright");
const { authenticate } = require("./smoke_auth.cjs");
const base = process.env.SMOKE_BASE_URL || "http://127.0.0.1:8001";
const role = process.env.SMOKE_ROLE;
const target = role === "admin" ? "/admin/" : "/recepcao/pre-consultas/";
let browser;

(async () => {
  browser = await chromium.launch({
    executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await authenticate(page, base + target);
  await page.screenshot({ path: `artifacts/permissions-${role}.png`, fullPage: true });
  if (role === "admin") {
    for (const path of ["/admin/preconsultas/clinic/", "/admin/auth/user/",
      "/admin/preconsultas/doctor/", "/admin/preconsultas/receptionprofile/"]) {
      const response = await page.goto(base + path);
      if (response.status() !== 200) throw new Error("Cadastro administrativo inacessível.");
    }
    const response = await page.goto(base + "/admin/preconsultas/consultation/");
    if (response.status() !== 404) throw new Error("Admin expôs consultas clínicas.");
  }
  for (const path of ["/medico/painel/", "/medico/pre-consultas/demo/",
    "/medico/pre-consultas/demo/anexos/pdf-exames-laboratoriais/status/",
    "/medico/pre-consultas/demo/anexos/pdf-exames-laboratoriais/conteudo/"]) {
    const response = await page.goto(base + path);
    if (response.status() !== 403) throw new Error("Perfil sem vínculo médico acessou conteúdo clínico.");
  }
  console.log(JSON.stringify({ role, operationalOrAdminScreen: true, clinicalAccessDenied: true }));
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close();
});
