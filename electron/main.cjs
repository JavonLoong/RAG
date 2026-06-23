const { app, BrowserWindow, Menu, shell, ipcMain, dialog } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { fileURLToPath } = require("node:url");

const REPO_ROOT = path.resolve(__dirname, "..");
const SERVER_DIR = path.join(REPO_ROOT, "api_server", "current_console");
const SERVER_SCRIPT = path.join(SERVER_DIR, "server.py");
const SERVER_HOST = process.env.POWER_RAG_HOST || "127.0.0.1";
const SERVER_PORT = Number(process.env.POWER_RAG_PORT || 8000);
const APP_URL = `http://${SERVER_HOST}:${SERVER_PORT}`;
const HEALTH_URL = `${APP_URL}/api/health`;
const LOG_DIR = path.join(REPO_ROOT, "storage_layer", "runtime", "current_console", "logs");
const ELECTRON_LOG = path.join(LOG_DIR, "electron-backend.log");
const SMOKE_TEST = process.env.POWER_RAG_DESKTOP_SMOKE === "1";
const ELECTRON_USER_DATA = path.join(
  REPO_ROOT,
  "storage_layer",
  "runtime",
  "current_console",
  SMOKE_TEST ? "electron-user-data-smoke" : "electron-user-data",
);
const INTERNAL_HTML_DIR = path.join(ELECTRON_USER_DATA, "internal-pages");

function numericEnv(name, fallback, options = {}) {
  const raw = Number(process.env[name]);
  const min = Number.isFinite(options.min) ? options.min : Number.NEGATIVE_INFINITY;
  const max = Number.isFinite(options.max) ? options.max : Number.POSITIVE_INFINITY;
  if (!Number.isFinite(raw)) return fallback;
  return Math.min(max, Math.max(min, Math.round(raw)));
}

function envFlag(name, fallback) {
  const raw = process.env[name];
  if (raw == null || raw === "") return fallback;
  return !["0", "false", "False", "no", "off"].includes(String(raw).trim());
}

const RENDERER_OLD_SPACE_MB = numericEnv("POWER_RAG_RENDERER_OLD_SPACE_MB", 8192, { min: 2048, max: 32768 });
const DISK_CACHE_MB = numericEnv("POWER_RAG_DISK_CACHE_MB", 2048, { min: 256, max: 32768 });
const DISABLE_BACKGROUND_THROTTLING = envFlag("POWER_RAG_DISABLE_BACKGROUND_THROTTLING", true);
const ENABLE_GPU_TUNING = envFlag("POWER_RAG_ENABLE_GPU_TUNING", false);
const POWER_RAG_CORPUS_FILE_NAMES = (process.env.POWER_RAG_CORPUS_FILE_NAMES || "power_rag_corpus.json,rag_corpus.json,chunks_rag.json")
  .split(",")
  .map((item) => item.trim())
  .filter(Boolean);
const WECHAT_RAG_CORPUS_FILE_NAMES = (
  process.env.POWER_RAG_WECHAT_CORPUS_FILE_NAMES || "wechat_private_chunks_rag.json,wechat_private_chunks.json,wechat_private.json"
)
  .split(",")
  .map((item) => item.trim())
  .filter(Boolean);
const POWER_RAG_CORPUS_BASE_DIR = process.env.POWER_RAG_CORPUS_BASE_DIR || REPO_ROOT;
const PREFERRED_POWER_RAG_CORPUS_DIRS = (process.env.POWER_RAG_CORPUS_DIRS || "")
  .split(";")
  .map((item) => item.trim())
  .filter(Boolean);
const PREFERRED_WECHAT_RAG_CORPUS_DIRS = (process.env.POWER_RAG_WECHAT_CORPUS_DIRS || process.env.POWER_RAG_CORPUS_DIRS || "")
  .split(";")
  .map((item) => item.trim())
  .filter(Boolean);

function configureChromiumForLargeLocalWorkloads() {
  app.commandLine.appendSwitch("js-flags", `--max-old-space-size=${RENDERER_OLD_SPACE_MB}`);
  app.commandLine.appendSwitch("disk-cache-size", String(DISK_CACHE_MB * 1024 * 1024));
  app.commandLine.appendSwitch("media-cache-size", String(Math.max(128, Math.floor(DISK_CACHE_MB / 4)) * 1024 * 1024));

  if (DISABLE_BACKGROUND_THROTTLING) {
    app.commandLine.appendSwitch("disable-background-timer-throttling");
    app.commandLine.appendSwitch("disable-renderer-backgrounding");
    app.commandLine.appendSwitch("disable-backgrounding-occluded-windows");
    app.commandLine.appendSwitch("disable-features", "CalculateNativeWinOcclusion");
  }

  if (ENABLE_GPU_TUNING) {
    app.commandLine.appendSwitch("enable-gpu-rasterization");
  }
}

fs.mkdirSync(ELECTRON_USER_DATA, { recursive: true });
app.setPath("userData", ELECTRON_USER_DATA);
configureChromiumForLargeLocalWorkloads();

let mainWindow = null;
let backendProcess = null;
let ownsBackendProcess = false;
const backendOutput = [];

function appendBackendOutput(chunk) {
  const text = chunk.toString();
  backendOutput.push(text);
  while (backendOutput.length > 80) {
    backendOutput.shift();
  }

  try {
    fs.mkdirSync(LOG_DIR, { recursive: true });
    fs.appendFileSync(ELECTRON_LOG, text, "utf8");
  } catch {
    // Logging must not prevent the desktop shell from starting.
  }
}

function isNavigationAbort(error) {
  const text = String(error && (error.message || error));
  return text.includes("ERR_ABORTED") || text.includes("(-3)");
}

function isInternalHtmlUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "file:") return false;
    const filePath = path.resolve(fileURLToPath(parsed));
    const internalDir = path.resolve(INTERNAL_HTML_DIR);
    return filePath === internalDir || filePath.startsWith(`${internalDir}${path.sep}`);
  } catch {
    return false;
  }
}

async function loadInternalHtml(name, html) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  fs.mkdirSync(INTERNAL_HTML_DIR, { recursive: true });
  const filePath = path.join(INTERNAL_HTML_DIR, `${name}.html`);
  fs.writeFileSync(filePath, html, "utf8");
  try {
    await mainWindow.loadFile(filePath);
  } catch (error) {
    if (!isNavigationAbort(error)) {
      throw error;
    }
    appendBackendOutput(`[${new Date().toISOString()}] ignored aborted internal page navigation: ${error.message}\n`);
  }
}

function uniqueExistingPaths(paths) {
  const seen = new Set();
  const output = [];
  for (const itemPath of paths) {
    if (!itemPath || seen.has(itemPath)) continue;
    seen.add(itemPath);
    if (fs.existsSync(itemPath)) output.push(itemPath);
  }
  return output;
}

function findDefaultPowerRagCorpus() {
  return findDefaultCorpusFile({
    fileNames: POWER_RAG_CORPUS_FILE_NAMES,
    preferredDirs: PREFERRED_POWER_RAG_CORPUS_DIRS,
    baseDir: POWER_RAG_CORPUS_BASE_DIR,
  });
}

function findDefaultWechatRagCorpus() {
  return findDefaultCorpusFile({
    fileNames: WECHAT_RAG_CORPUS_FILE_NAMES,
    preferredDirs: PREFERRED_WECHAT_RAG_CORPUS_DIRS,
    baseDir: POWER_RAG_CORPUS_BASE_DIR,
  });
}

function findDefaultCorpusFile({ fileNames, preferredDirs, baseDir }) {
  const candidates = [];
  for (const dir of preferredDirs) {
    for (const fileName of fileNames) {
      candidates.push(path.join(dir, fileName));
    }
  }

  try {
    if (fs.existsSync(baseDir)) {
      for (const fileName of fileNames) {
        candidates.push(path.join(baseDir, fileName));
      }
      for (const entry of fs.readdirSync(baseDir, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue;
        for (const fileName of fileNames) {
          candidates.push(path.join(baseDir, entry.name, fileName));
        }
      }
    }
  } catch (error) {
    appendBackendOutput(`[${new Date().toISOString()}] default corpus scan failed: ${error.message}\n`);
  }

  return uniqueExistingPaths(candidates)
    .map((filePath) => ({ filePath, stat: fs.statSync(filePath) }))
    .sort((a, b) => b.stat.mtimeMs - a.stat.mtimeMs)[0]?.filePath || null;
}

async function descriptorForLocalFile(filePath) {
  const stat = await fs.promises.stat(filePath);
  const bytes = await fs.promises.readFile(filePath);
  return {
    path: filePath,
    name: path.basename(filePath),
    size: stat.size,
    lastModified: Math.round(stat.mtimeMs),
    bytes,
  };
}

function registerDesktopIpcHandlers() {
  ipcMain.handle("power-rag:pick-power-rag-corpus", async (_event, options = {}) => {
    return pickCorpusFile({
      options,
      defaultPath: findDefaultPowerRagCorpus(),
      title: "选择 PowerRAG JSON 语料",
    });
  });
  ipcMain.handle("power-rag:pick-wechat-rag-corpus", async (_event, options = {}) => {
    return pickCorpusFile({
      options,
      defaultPath: findDefaultWechatRagCorpus(),
      title: "选择微信私聊 RAG JSON 语料",
    });
  });
}

async function pickCorpusFile({ options = {}, defaultPath = null, title }) {
  const preferDefault = options && options.preferDefault !== false;
  if (preferDefault && defaultPath) {
    return descriptorForLocalFile(defaultPath);
  }

  const result = await dialog.showOpenDialog(mainWindow, {
    title,
    defaultPath: defaultPath || POWER_RAG_CORPUS_BASE_DIR,
    properties: ["openFile"],
    filters: [
      { name: "RAG JSON", extensions: ["json", "jsonl", "ndjson"] },
      { name: "All Files", extensions: ["*"] },
    ],
  });
  if (result.canceled || !result.filePaths?.length) {
    return null;
  }
  return descriptorForLocalFile(result.filePaths[0]);
}

function requestStatus(url, timeoutMs = 1200) {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: timeoutMs }, (response) => {
      response.resume();
      resolve(response.statusCode || 0);
    });
    request.on("timeout", () => {
      request.destroy();
      resolve(0);
    });
    request.on("error", () => resolve(0));
  });
}

async function isBackendHealthy() {
  const status = await requestStatus(HEALTH_URL);
  return status >= 200 && status < 300;
}

function commandExists(command, args = ["--version"]) {
  const result = spawnSync(command, args, {
    cwd: REPO_ROOT,
    encoding: "utf8",
    windowsHide: true,
  });
  return result.status === 0;
}

function resolvePythonCommand() {
  const envPython = process.env.POWER_RAG_PYTHON;
  if (envPython && fs.existsSync(envPython)) {
    return { command: envPython, argsPrefix: [] };
  }

  const venvPython = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  if (fs.existsSync(venvPython)) {
    return { command: venvPython, argsPrefix: [] };
  }

  if (commandExists("py", ["-3", "--version"])) {
    return { command: "py", argsPrefix: ["-3"] };
  }

  if (commandExists("python", ["--version"])) {
    return { command: "python", argsPrefix: [] };
  }

  if (commandExists("python3", ["--version"])) {
    return { command: "python3", argsPrefix: [] };
  }

  return null;
}

function backendEnvironment() {
  const pythonPathParts = [
    path.join(SERVER_DIR, "chroma_rag_poc", "src"),
    REPO_ROOT,
    process.env.PYTHONPATH || "",
  ].filter(Boolean);

  return {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    PYTHONPATH: pythonPathParts.join(path.delimiter),
  };
}

async function startBackendIfNeeded() {
  if (await isBackendHealthy()) {
    return { reusedExisting: true };
  }

  const python = resolvePythonCommand();
  if (!python) {
    throw new Error("No usable Python executable found. Install dependencies or set POWER_RAG_PYTHON.");
  }

  if (!fs.existsSync(SERVER_SCRIPT)) {
    throw new Error(`Backend entrypoint does not exist: ${SERVER_SCRIPT}`);
  }

  fs.mkdirSync(LOG_DIR, { recursive: true });
  fs.writeFileSync(
    ELECTRON_LOG,
    `[${new Date().toISOString()}] Starting backend with ${python.command}\n`,
    "utf8",
  );

  backendProcess = spawn(python.command, [...python.argsPrefix, SERVER_SCRIPT], {
    cwd: SERVER_DIR,
    env: backendEnvironment(),
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  ownsBackendProcess = true;

  backendProcess.stdout.on("data", appendBackendOutput);
  backendProcess.stderr.on("data", appendBackendOutput);
  backendProcess.on("exit", (code, signal) => {
    appendBackendOutput(`\n[${new Date().toISOString()}] backend exited code=${code} signal=${signal}\n`);
  });

  const startedAt = Date.now();
  const timeoutMs = Number(process.env.POWER_RAG_BACKEND_TIMEOUT_MS || 90000);
  while (Date.now() - startedAt < timeoutMs) {
    if (await isBackendHealthy()) {
      return { reusedExisting: false };
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }

  throw new Error(`Backend startup timed out. Log: ${ELECTRON_LOG}`);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function loadingHtml() {
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>PowerRAG 正在启动</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
      color: #172033;
      background: #f5f7fb;
    }
    main {
      width: min(560px, calc(100vw - 48px));
      padding: 28px;
      border: 1px solid #dfe6f2;
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 14px 40px rgba(17, 31, 58, 0.08);
    }
    h1 { margin: 0 0 12px; font-size: 22px; }
    p { margin: 0; color: #5d6b82; line-height: 1.7; }
  </style>
</head>
<body>
  <main>
    <h1>PowerRAG 正在启动本地后端</h1>
    <p>正在检查 ${HEALTH_URL}。后端可用后会自动进入控制台。</p>
  </main>
</body>
</html>`;
}

function errorHtml(error) {
  const details = escapeHtml([String(error && error.stack ? error.stack : error), ...backendOutput].join("\n"));
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>PowerRAG 启动失败</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
      color: #172033;
      background: #fff7f7;
    }
    main { max-width: 920px; margin: 48px auto; padding: 0 24px; }
    h1 { margin: 0 0 12px; font-size: 24px; }
    p { color: #5d2930; line-height: 1.7; }
    pre {
      max-height: 56vh;
      overflow: auto;
      padding: 16px;
      border: 1px solid #efc4c8;
      border-radius: 8px;
      background: #fff;
      white-space: pre-wrap;
      word-break: break-word;
    }
  </style>
</head>
<body>
  <main>
    <h1>PowerRAG 后端启动失败</h1>
    <p>请检查 Python 环境，或确认端口 ${SERVER_PORT} 没有被非 PowerRAG 服务占用。完整日志保存在：${escapeHtml(ELECTRON_LOG)}</p>
    <pre>${details}</pre>
  </main>
</body>
</html>`;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 720,
    title: "PowerRAG",
    backgroundColor: "#f5f7fb",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: !DISABLE_BACKGROUND_THROTTLING,
      spellcheck: false,
      v8CacheOptions: "code",
    },
  });

  mainWindow.once("ready-to-show", () => {
    if (!SMOKE_TEST) {
      mainWindow.show();
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(APP_URL)) {
      return { action: "allow" };
    }
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(APP_URL) && !isInternalHtmlUrl(url)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    appendBackendOutput(
      `\n[${new Date().toISOString()}] renderer gone reason=${details.reason} exitCode=${details.exitCode}\n`,
    );
  });

  void loadInternalHtml("loading", loadingHtml()).catch((error) => {
    appendBackendOutput(`[${new Date().toISOString()}] loading page failed: ${error.stack || error}\n`);
  });
}

async function boot() {
  createWindow();
  appendBackendOutput(
    `[${new Date().toISOString()}] Desktop performance profile: renderer_old_space=${RENDERER_OLD_SPACE_MB}MB, disk_cache=${DISK_CACHE_MB}MB, background_throttling=${!DISABLE_BACKGROUND_THROTTLING}, gpu_tuning=${ENABLE_GPU_TUNING}, user_data=${ELECTRON_USER_DATA}\n`,
  );

  try {
    const result = await startBackendIfNeeded();
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setTitle(result.reusedExisting ? "PowerRAG - connected" : "PowerRAG");
      await mainWindow.loadURL(APP_URL);
      if (SMOKE_TEST) {
        app.quit();
      }
    }
  } catch (error) {
    process.exitCode = 1;
    if (mainWindow && !mainWindow.isDestroyed()) {
      try {
        await loadInternalHtml("startup-error", errorHtml(error));
      } catch (loadError) {
        appendBackendOutput(`[${new Date().toISOString()}] startup error page failed: ${loadError.stack || loadError}\n`);
      }
    }
    if (SMOKE_TEST) {
      app.quit();
    }
  }
}

function stopBackend() {
  if (!backendProcess || !ownsBackendProcess) {
    return;
  }

  try {
    backendProcess.kill();
  } catch {
    // Process may already be gone.
  }
  backendProcess = null;
}

Menu.setApplicationMenu(null);
registerDesktopIpcHandlers();

app.whenReady().then(boot);

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", stopBackend);

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    boot();
  }
});
