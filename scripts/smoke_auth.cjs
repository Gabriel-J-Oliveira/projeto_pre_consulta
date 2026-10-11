function requireCredential(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} é obrigatório para os smoke tests autenticados.`);
  }
  return value;
}

async function authenticate(page, targetUrl) {
  const username = requireCredential("SMOKE_USERNAME");
  const password = requireCredential("SMOKE_PASSWORD");
  const target = new URL(targetUrl);
  const login = new URL("/accounts/login/", target.origin);
  login.searchParams.set("next", `${target.pathname}${target.search}`);

  const loginResponse = await page.goto(login.toString(), { waitUntil: "networkidle" });
  if (!loginResponse || loginResponse.status() !== 200) {
    throw new Error("A tela de login não retornou 200.");
  }

  await page.locator('[name="username"]').fill(username);
  await page.locator('[name="password"]').fill(password);
  const [response] = await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator('.auth-form button[type="submit"]').click(),
  ]);

  if (!response || response.status() !== 200 || page.url() !== targetUrl) {
    throw new Error("O login não retornou à tela interna solicitada.");
  }
  return response;
}

module.exports = { authenticate };
