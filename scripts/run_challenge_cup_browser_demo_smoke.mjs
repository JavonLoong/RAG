import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const __filename = fileURLToPath(import.meta.url);
const REPO_ROOT = path.resolve(path.dirname(__filename), "..");
const BASE_URL = process.env.RAG_BROWSER_SMOKE_URL || "http://127.0.0.1:8000";
const PYTHON = process.env.PYTHON || "python";
const REPORT_DIR = path.join(REPO_ROOT, "docs", "challenge_cup", "reproducibility");
const SCREENSHOT_DIR = path.join(REPORT_DIR, "browser_screenshots");
const OUTPUT_DIR = path.join(REPO_ROOT, "outputs", "challenge-cup-browser-smoke");
const REPORT_JSON = path.join(REPORT_DIR, "browser_demo_smoke_report.json");
const REPORT_MD = path.join(REPORT_DIR, "browser_demo_smoke_report.md");
const QUERY = "燃气轮机异常振动诊断流程";
const EXPECTED_RECORD_IDS = [
  "demo-maint-thresholds-076",
  "demo-structure-fault-130",
  "demo-gt07-fault-021",
  "demo-gt07-repair-022",
  "demo-gt07-manual-023",
];
const KG_DELIVERABLE_BASE_PATH = "/deliverables/06_四本书KG工具跑通演示/";
const REQUIRED_STATIC_ROUTES = [
  { name: "libs route", pathname: "/libs/d3.min.js" },
  { name: "assets route", pathname: "/assets/hero-gas-turbine-rag.webp" },
  { name: "deliverables route", pathname: `${KG_DELIVERABLE_BASE_PATH}knowledge_graph.svg` },
];

function fileExists(filePath) {
  try {
    return fs.existsSync(filePath);
  } catch {
    return false;
  }
}

function tryRequire(specifier) {
  try {
    return require(specifier);
  } catch {
    return null;
  }
}

function candidatePlaywrightModuleDirs() {
  const dirs = [];
  for (const item of (process.env.NODE_PATH || "").split(path.delimiter).filter(Boolean)) {
    dirs.push(item);
  }

  const bundledRoot = path.join(
    os.homedir(),
    ".cache",
    "codex-runtimes",
    "codex-primary-runtime",
    "dependencies",
    "node",
    "node_modules",
  );
  dirs.push(bundledRoot);

  for (const root of [...dirs]) {
    const pnpmRoot = path.join(root, ".pnpm");
    if (!fileExists(pnpmRoot)) continue;
    for (const name of fs.readdirSync(pnpmRoot)) {
      if (name.startsWith("playwright@")) {
        dirs.push(path.join(pnpmRoot, name, "node_modules"));
      }
    }
  }
  return [...new Set(dirs)];
}

function loadPlaywright() {
  const direct = tryRequire("playwright");
  if (direct) return { playwright: direct, source: "project node_modules" };

  for (const moduleDir of candidatePlaywrightModuleDirs()) {
    const packageDir = path.join(moduleDir, "playwright");
    if (!fileExists(packageDir)) continue;
    const loaded = tryRequire(packageDir);
    if (loaded) return { playwright: loaded, source: packageDir };
  }

  throw new Error(
    "Playwright is not available. Install it with `npm install --save-dev playwright` or run inside Codex bundled runtime.",
  );
}

async function getJson(url, timeoutMs = 2000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function waitForHealth(serverProcess) {
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    if (serverProcess?.exitCode !== null) {
      throw new Error(`server.py exited before health check passed; exitCode=${serverProcess.exitCode}`);
    }
    const health = await getJson(`${BASE_URL}/api/health`, 2000);
    if (health?.status === "ok") return health;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${BASE_URL}/api/health`);
}

async function ensureServer() {
  const existing = await getJson(`${BASE_URL}/api/health`, 1000);
  if (existing?.status === "ok") return { started: false, health: existing, process: null };

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const stdout = fs.openSync(path.join(OUTPUT_DIR, "server.out.log"), "w");
  const stderr = fs.openSync(path.join(OUTPUT_DIR, "server.err.log"), "w");
  const serverProcess = spawn(PYTHON, ["api_server/current_console/server.py"], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    stdio: ["ignore", stdout, stderr],
    windowsHide: true,
  });
  const health = await waitForHealth(serverProcess);
  return { started: true, health, process: serverProcess };
}

function rel(filePath) {
  return path.relative(REPO_ROOT, filePath).replaceAll(path.sep, "/");
}

function check(name, passed, detail) {
  return { name, passed: Boolean(passed), detail };
}

function routeUrl(pathname) {
  return new URL(encodeURI(pathname), BASE_URL).href;
}

async function checkHttpRoute(name, pathname) {
  const url = routeUrl(pathname);
  try {
    const response = await fetch(url);
    return check(name, response.ok, `GET ${pathname} -> ${response.status}`);
  } catch (error) {
    return check(name, false, `GET ${pathname} -> ${error.message || error}`);
  }
}

async function verifyStaticRoutes() {
  return Promise.all(REQUIRED_STATIC_ROUTES.map((item) => checkHttpRoute(item.name, item.pathname)));
}

function recordSameOriginRequestFailure(events, request) {
  try {
    if (new URL(request.url()).origin !== new URL(BASE_URL).origin) return;
  } catch {
    return;
  }
  events.push({ type: "requestfailed", text: `${request.method()} ${request.url()} ${request.failure()?.errorText}` });
}

async function runBrowserSmoke(playwright, playwrightSource) {
  const { chromium } = playwright;
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const desktopConsole = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "zh-CN" });
  page.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) {
      desktopConsole.push({ type: msg.type(), text: msg.text(), location: msg.location() });
    }
  });
  page.on("pageerror", (err) => desktopConsole.push({ type: "pageerror", text: err.message }));
  page.on("requestfailed", (req) => recordSameOriginRequestFailure(desktopConsole, req));

  await page.goto(`${BASE_URL}/`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await page.waitForSelector("#page-overview.active", { timeout: 15_000 });
  const title = await page.title();
  const overviewText = (await page.locator("body").innerText({ timeout: 10_000 })).slice(0, 1400);
  const desktopOverview = path.join(SCREENSHOT_DIR, "desktop_overview.png");
  await page.screenshot({ path: desktopOverview, fullPage: false });

  await page.locator('[data-page="search"]').click();
  await page.waitForSelector("#page-search.active", { timeout: 10_000 });
  await page.fill("#searchInput", QUERY);
  await page.fill("#searchTopK", "5");
  await page.click("#btnSearch");
  await page.waitForFunction(() => {
    const results = document.querySelector("#searchResults");
    return results && results.innerText && results.innerText.trim().length > 30 && !results.innerText.includes("输入问题后");
  }, null, { timeout: 15_000 });
  const searchMeta = await page.locator("#searchMeta").innerText().catch(() => "");
  const resultsText = await page.locator("#searchResults").innerText().catch(() => "");
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.locator("#searchResults").evaluate((node) => node.scrollIntoView({ block: "start", inline: "nearest" }));
  await page.waitForTimeout(250);
  const searchResultCards = await page.locator("#searchResults .result-card").evaluateAll((cards) => cards.map((card) => {
    const rect = card.getBoundingClientRect();
    const text = card.innerText || "";
    const recordId = text.match(/record\s+([^\s]+)/)?.[1] || "";
    return {
      record_id: recordId,
      visible: rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth,
      top: Math.round(rect.top),
      bottom: Math.round(rect.bottom),
    };
  }));
  const visibleRecordIds = searchResultCards.filter((item) => item.visible && item.record_id).map((item) => item.record_id);
  const searchResultsVisible = EXPECTED_RECORD_IDS.every((recordId) => visibleRecordIds.includes(recordId));
  const desktopSearch = path.join(SCREENSHOT_DIR, "desktop_search_results.png");
  await page.screenshot({ path: desktopSearch, fullPage: false });

  await page.locator('#globalModeToggle [data-mode="graphrag"]').click();
  await page.waitForSelector('.nav-item[data-page="kg"]:not(.is-hidden)', { timeout: 10_000 });
  await page.locator('.nav-item[data-page="kg"]').click();
  await page.waitForSelector("#page-kg.active", { timeout: 10_000 });
  await page.waitForSelector("#kgArtifacts a", { timeout: 10_000 });
  await page.waitForFunction(() => {
    const img = document.querySelector("#kgGraphImage");
    return img && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0;
  }, null, { timeout: 15_000 });
  const kgImage = await page.locator("#kgGraphImage").evaluate((img) => ({
    width: img.naturalWidth,
    height: img.naturalHeight,
    src: img.currentSrc || img.src,
  }));
  const artifactLinks = await page.locator("#kgArtifacts a").evaluateAll((links) => links.map((link) => ({
    label: link.closest(".kg-artifact-row")?.innerText || link.innerText,
    href: link.href,
  })));
  const artifactStatuses = [];
  for (const artifact of artifactLinks) {
    const response = await page.request.get(artifact.href);
    artifactStatuses.push({ ...artifact, status: response.status(), ok: response.ok() });
  }
  await page.locator("#kgArtifacts").scrollIntoViewIfNeeded();
  await page.waitForTimeout(250);
  const desktopKgArtifacts = path.join(SCREENSHOT_DIR, "desktop_kg_artifacts.png");
  await page.screenshot({ path: desktopKgArtifacts, fullPage: false });

  const mobileConsole = [];
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, locale: "zh-CN" });
  mobile.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) {
      mobileConsole.push({ type: msg.type(), text: msg.text(), location: msg.location() });
    }
  });
  mobile.on("pageerror", (err) => mobileConsole.push({ type: "pageerror", text: err.message }));
  mobile.on("requestfailed", (req) => recordSameOriginRequestFailure(mobileConsole, req));
  await mobile.goto(`${BASE_URL}/`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await mobile.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await mobile.waitForSelector("#page-overview.active", { timeout: 15_000 });
  const mobileText = (await mobile.locator("body").innerText({ timeout: 10_000 })).slice(0, 900);
  const mobileOverview = path.join(SCREENSHOT_DIR, "mobile_overview.png");
  await mobile.screenshot({ path: mobileOverview, fullPage: false });

  await browser.close();

  const checks = [
    check("page identity", title === "动力装备知识库控制台", `title=${title}`),
    check("desktop not blank", overviewText.includes("动力装备知识库") && overviewText.includes("语义检索"), "desktop overview contains app content"),
    check("desktop console health", desktopConsole.length === 0, `${desktopConsole.length} warning/error console events`),
    check("search interaction", searchMeta.includes("结果 5") && resultsText.includes("GT-07"), searchMeta),
    check(
      "search results visible",
      searchResultsVisible,
      `visible records ${visibleRecordIds.length}/${EXPECTED_RECORD_IDS.length}: ${visibleRecordIds.join(", ")}`,
    ),
    check("KG SVG render", kgImage.width > 0 && kgImage.height > 0, `${kgImage.width}x${kgImage.height}`),
    check(
      "KG artifact links",
      artifactStatuses.length === 4 && artifactStatuses.every((item) => item.ok),
      artifactStatuses.map((item) => `${path.basename(new URL(item.href).pathname)}:${item.status}`).join(", "),
    ),
    check("mobile not blank", mobileText.includes("动力装备知识库") && mobileText.includes("演示数据"), "mobile overview contains app content"),
    check("mobile console health", mobileConsole.length === 0, `${mobileConsole.length} warning/error console events`),
  ];

  return {
    playwright_source: playwrightSource,
    title,
    query: QUERY,
    overview_preview: overviewText,
    search_meta: searchMeta,
    results_preview: resultsText.slice(0, 1400),
    search_results_visible: searchResultsVisible,
    visible_record_ids: visibleRecordIds,
    search_result_card_count: searchResultCards.length,
    search_result_cards: searchResultCards,
    kg_image: kgImage,
    kg_artifacts: artifactStatuses,
    mobile_preview: mobileText,
    desktop_console: desktopConsole,
    mobile_console: mobileConsole,
    screenshots: {
      desktop_overview: rel(desktopOverview),
      desktop_search_results: rel(desktopSearch),
      desktop_kg_artifacts: rel(desktopKgArtifacts),
      mobile_overview: rel(mobileOverview),
    },
    checks,
  };
}

function writeReports(payload) {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  fs.writeFileSync(REPORT_JSON, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

  const lines = [
    "# Browser Demo Smoke Report",
    "",
    `- Status: \`${payload.status}\``,
    `- Passed: ${payload.passed}/${payload.total}`,
    `- URL: ${payload.base_url}`,
    `- Query: ${payload.browser.query}`,
    `- Playwright: ${payload.browser.playwright_source}`,
    "",
    "| Check | Result | Detail |",
    "| --- | --- | --- |",
    ...payload.checks.map((item) => `| ${item.name} | ${item.passed ? "pass" : "fail"} | ${String(item.detail).replaceAll("|", "/")} |`),
    "",
    "## Evidence",
    "",
    `- Desktop overview screenshot: \`${payload.browser.screenshots.desktop_overview}\``,
    `- Desktop search screenshot: \`${payload.browser.screenshots.desktop_search_results}\``,
    `- Desktop KG artifacts screenshot: \`${payload.browser.screenshots.desktop_kg_artifacts}\``,
    `- Mobile overview screenshot: \`${payload.browser.screenshots.mobile_overview}\``,
    "",
    "## Static Route Checks",
    "",
    "| Route | Result | Detail |",
    "| --- | --- | --- |",
    ...(payload.static_routes || []).map((item) => `| ${item.name} | ${item.passed ? "pass" : "fail"} | ${String(item.detail).replaceAll("|", "/")} |`),
    "",
    "## Search Result Preview",
    "",
    `Visible record ids: ${payload.browser.visible_record_ids.join(", ")}`,
    "",
    "```text",
    payload.browser.results_preview,
    "```",
  ];
  fs.writeFileSync(REPORT_MD, `${lines.join("\n").trim()}\n`, "utf8");
}

async function main() {
  const { playwright, source } = loadPlaywright();
  let server = null;
  try {
    server = await ensureServer();
    const staticRoutes = await verifyStaticRoutes();
    const browser = await runBrowserSmoke(playwright, source);
    const checks = [
      check("health endpoint", server.health?.status === "ok", `GET /api/health -> ${server.health?.status || "unknown"}`),
      ...staticRoutes,
      ...browser.checks,
    ];
    const passed = checks.filter((item) => item.passed).length;
    const payload = {
      report_type: "challenge_cup_browser_demo_smoke",
      generated_at: new Date().toISOString(),
      status: passed === checks.length ? "pass" : "fail",
      passed,
      total: checks.length,
      base_url: BASE_URL,
      server_started_by_script: server.started,
      checks,
      static_routes: staticRoutes,
      browser,
    };
    writeReports(payload);
    console.log(`Wrote ${rel(REPORT_MD)}`);
    console.log(`Status: ${payload.status} (${payload.passed}/${payload.total} checks)`);
    process.exitCode = payload.status === "pass" ? 0 : 1;
  } finally {
    if (server?.started && server.process && server.process.exitCode === null) {
      server.process.kill();
    }
  }
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
