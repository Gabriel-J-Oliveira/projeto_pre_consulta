// Shared controlled selection; never download a browser or log launch credentials.
const fs = require("node:fs");
const path = require("node:path");

function browserOptions({ env = process.env, platform = process.platform,
  exists = fs.existsSync, chromiumPath } = {}) {
  if (env.SMOKE_BROWSER_PATH && env.SMOKE_BROWSER_CHANNEL) {
    throw new Error("Configure apenas SMOKE_BROWSER_PATH ou SMOKE_BROWSER_CHANNEL.");
  }
  if (env.SMOKE_BROWSER_PATH) {
    if (!path.isAbsolute(env.SMOKE_BROWSER_PATH) || !exists(env.SMOKE_BROWSER_PATH)) {
      throw new Error("SMOKE_BROWSER_PATH deve apontar a um navegador existente, com caminho absoluto.");
    }
    return { headless: true, executablePath: env.SMOKE_BROWSER_PATH };
  }
  if (env.SMOKE_BROWSER_CHANNEL) {
    if (!["chrome", "msedge", "chromium"].includes(env.SMOKE_BROWSER_CHANNEL)) {
      throw new Error("SMOKE_BROWSER_CHANNEL aceita somente chromium, chrome ou msedge.");
    }
    if (env.SMOKE_BROWSER_CHANNEL !== "chromium") {
      return { headless: true, channel: env.SMOKE_BROWSER_CHANNEL };
    }
    if (!chromiumPath || !exists(chromiumPath)) {
      throw new Error("Playwright Chromium não está provisionado; configure um navegador existente.");
    }
    return { headless: true, executablePath: chromiumPath };
  }
  if (chromiumPath && exists(chromiumPath)) {
    return { headless: true, executablePath: chromiumPath };
  }
  const candidates = platform === "win32" ? [
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  ] : [];
  const executablePath = candidates.find(candidate => exists(candidate));
  if (executablePath) return { headless: true, executablePath };
  throw new Error("Nenhum navegador provisionado. Configure SMOKE_BROWSER_PATH/CHANNEL ou Chromium já instalado; nenhum download automático será feito.");
}

async function launchBrowser() {
  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch { throw new Error("Playwright indisponível para o Node atual; confira a instalação e NODE_PATH. Nenhum navegador foi baixado."); }
  const options = browserOptions({ chromiumPath: chromium.executablePath() });
  try { return await chromium.launch(options); }
  catch { throw new Error("Não foi possível iniciar o navegador provisionado. Confira SMOKE_BROWSER_PATH/CHANNEL e as dependências locais; smoke não executado."); }
}

module.exports = { browserOptions, launchBrowser };
