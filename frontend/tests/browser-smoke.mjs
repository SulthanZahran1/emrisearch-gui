import { mkdtemp, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { chromium } from "playwright";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(frontendDir, "..");
const python = process.env.EMRI_PYTHON || "/home/dev/emrisearch-gui/.venv/bin/python";

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

async function freePort() {
  const server = createServer();
  await new Promise((resolvePromise, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolvePromise);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("could not reserve a local port");
  const port = address.port;
  await new Promise((resolvePromise) => server.close(resolvePromise));
  return port;
}

async function waitForHttp(url, child, stderr) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`backend exited before readiness: ${stderr.join("")}`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Uvicorn is still starting.
    }
    await sleep(100);
  }
  throw new Error(`timed out waiting for ${url}: ${stderr.join("")}`);
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolvePromise) => child.once("exit", resolvePromise)),
    sleep(5_000),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function main() {
  const fixtureRoot = await mkdtemp(join("/tmp", "emrisearch-gui-browser-"));
  let backend;
  let browser;
  const stderr = [];
  try {
    const fixture = spawnSync(
      python,
      ["-c", "from pathlib import Path; import sys; from backend.emri.fixtures import make_run_chain; make_run_chain(Path(sys.argv[1]), 3)", fixtureRoot],
      { cwd: repoRoot, encoding: "utf8" },
    );
    if (fixture.status !== 0) {
      throw new Error(`fixture creation failed: ${fixture.stderr || fixture.stdout}`);
    }

    const port = await freePort();
    backend = spawn(
      python,
      ["-m", "uvicorn", "backend.api.app:app", "--host", "127.0.0.1", "--port", String(port)],
      {
        cwd: repoRoot,
        env: { ...process.env, EMRISEARCH_ROOT: fixtureRoot },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    backend.stderr.on("data", (chunk) => stderr.push(String(chunk)));
    await waitForHttp(`http://127.0.0.1:${port}/api/runs`, backend, stderr);

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const baseUrl = `http://127.0.0.1:${port}`;
    await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /stage_02/ }).waitFor();
    const runRows = await page.locator("button.run-row").count();
    if (runRows !== 3) throw new Error(`expected 3 fixture runs, found ${runRows}`);

    await page.getByRole("button", { name: /stage_02/ }).click();
    await page.getByRole("heading", { name: "stage_02" }).waitFor();
    await page.getByAltText("Corner plot for run stage_02").waitFor({ state: "visible" });
    await page.waitForFunction(
      () => Array.from(document.querySelectorAll(".plot-image img")).length === 2 &&
        Array.from(document.querySelectorAll(".plot-image img")).every((image) => image.complete && image.naturalWidth > 0),
      undefined,
      { timeout: 20_000 },
    );

    const cornerImage = page.getByAltText("Corner plot for run stage_02");
    const selects = page.locator("label.control-field select");
    await selects.nth(0).selectOption("100");
    await page.getByRole("checkbox", { name: "truth", exact: true }).uncheck();
    await page.getByRole("button", { name: "paper" }).first().click();
    const cornerUrl = await cornerImage.getAttribute("src");
    if (!cornerUrl?.includes("top_n=100") || !cornerUrl.includes("truth=false") || !cornerUrl.includes("theme=paper")) {
      throw new Error(`corner controls did not update request URL: ${cornerUrl}`);
    }

    const connectionImage = page.getByAltText("Connection plot for run stage_02");
    await selects.nth(1).selectOption("161");
    await selects.nth(2).selectOption("0.0,1.0");
    await page.getByRole("checkbox", { name: "progress", exact: true }).check();
    const connectionUrl = await connectionImage.getAttribute("src");
    if (!connectionUrl?.includes("n=161") || !connectionUrl.includes("t_range=0.0%2C1.0") || !connectionUrl.includes("progress=true")) {
      throw new Error(`connection controls did not update request URL: ${connectionUrl}`);
    }

    const download = page.getByRole("link", { name: "download PNG" }).first();
    if (!(await download.getAttribute("href"))?.includes("/plots/corner")) {
      throw new Error("corner download link is not tied to the corner request");
    }

    const beforeTheme = await page.locator("html").getAttribute("data-theme");
    await page.locator("button.theme-button").click();
    const shellTheme = await page.locator("html").getAttribute("data-theme");
    const expectedTheme = beforeTheme === "dark" ? "light" : "dark";
    if (shellTheme !== expectedTheme) throw new Error(`theme toggle did not change ${beforeTheme} to ${expectedTheme}: ${shellTheme}`);

    await page.setViewportSize({ width: 390, height: 844 });
    const mobileWidths = await page.evaluate(() => ({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }));
    if (mobileWidths.scrollWidth > mobileWidths.innerWidth) {
      throw new Error(`mobile horizontal overflow: ${JSON.stringify(mobileWidths)}`);
    }
    if (consoleErrors.length || pageErrors.length) {
      throw new Error(`browser errors: ${JSON.stringify({ consoleErrors, pageErrors })}`);
    }

    console.log(JSON.stringify({
      ok: true,
      runRows,
      detail: "stage_02",
      cornerUrl,
      connectionUrl,
      shellTheme,
      mobileWidths,
      consoleErrors,
      pageErrors,
    }, null, 2));
  } finally {
    if (browser) await browser.close();
    await stopProcess(backend);
    await rm(fixtureRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
