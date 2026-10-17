const { test } = require("node:test");
const assert = require("node:assert/strict");
const { browserOptions } = require("./smoke_browser.cjs");
const defaults = { env: {}, platform: "linux", exists: () => false, chromiumPath: "/fake/chromium" };
test("explicit existing path wins without auto detection", () => {
  assert.equal(browserOptions({ ...defaults, env: { SMOKE_BROWSER_PATH: "/fake/browser" }, exists: () => true }).executablePath, "/fake/browser");
});
test("nonexistent or relative explicit path fails", () => {
  for (const value of ["/missing/browser", "relative-browser"]) {
    assert.throws(() => browserOptions({ ...defaults, env: { SMOKE_BROWSER_PATH: value } }), /SMOKE_BROWSER_PATH/);
  }
});
test("explicit choice is never silently replaced", () => {
  assert.throws(() => browserOptions({ ...defaults, env: { SMOKE_BROWSER_PATH: "/fake/browser", SMOKE_BROWSER_CHANNEL: "chrome" } }), /apenas/);
  assert.throws(() => browserOptions({ ...defaults, env: { SMOKE_BROWSER_CHANNEL: "unknown" } }), /somente/);
});
test("Chrome and Edge channels are passed to Playwright", () => {
  for (const channel of ["chrome", "msedge"]) assert.equal(browserOptions({ ...defaults, env: { SMOKE_BROWSER_CHANNEL: channel } }).channel, channel);
});
test("installed Chromium works on non Windows platforms", () => {
  assert.equal(browserOptions({ ...defaults, exists: value => value === "/fake/chromium" }).executablePath, "/fake/chromium");
});
test("explicit missing Chromium fails, no download or Edge fallback", () => {
  assert.throws(() => browserOptions({ ...defaults, env: { SMOKE_BROWSER_CHANNEL: "chromium" } }), /não está provisionado/);
});
test("controlled Windows detection preserves existing Edge support", () => {
  const edge = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
  assert.equal(browserOptions({ ...defaults, platform: "win32", exists: value => value === edge }).executablePath, edge);
});
test("missing browser gives actionable diagnostic", () => {
  assert.throws(() => browserOptions(defaults), /Nenhum navegador provisionado/);
});
