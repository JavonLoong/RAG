import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const codexHome = path.join(os.homedir(), ".codex");
const logPath = path.join(codexHome, "remote-control-keepalive.log");
const pidPath = path.join(codexHome, "remote-control-keepalive.pid");
const codexJs = path.join(
  process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming"),
  "npm",
  "node_modules",
  "@openai",
  "codex",
  "bin",
  "codex.js",
);

let child = null;
let nextId = 1;
let stdoutBuffer = "";
let lastStatus = null;
let shuttingDown = false;
let pollTimer = null;
let restartTimer = null;
let conflictSeen = false;

function log(message, data = undefined) {
  const suffix = data === undefined ? "" : ` ${JSON.stringify(data)}`;
  fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}${suffix}\n`, "utf8");
}

function statusForLog(status) {
  if (!status) {
    return null;
  }
  return {
    status: status.status,
    serverName: status.serverName,
    environmentId: status.environmentId,
  };
}

function writeMessage(message) {
  if (!child || !child.stdin.writable) {
    return;
  }
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

function send(method, params) {
  const message = { jsonrpc: "2.0", id: String(nextId++), method };
  if (params !== undefined) {
    message.params = params;
  }
  writeMessage(message);
}

function notify(method, params) {
  const message = { jsonrpc: "2.0", method };
  if (params !== undefined) {
    message.params = params;
  }
  writeMessage(message);
}

function handleStatus(status, source) {
  lastStatus = status;
  log(`remote status ${source}`, statusForLog(status));

  if (status.status === "errored" && !shuttingDown) {
    log("remote status errored; restarting app-server");
    restartChild(5000);
  }
}

function handleMessage(message) {
  if (message.method === "remoteControl/status/changed") {
    handleStatus(message.params, "notification");
    return;
  }

  if (message.error) {
    log("json-rpc error", message.error);
    return;
  }

  if (message.result && Object.hasOwn(message.result, "status")) {
    handleStatus(message.result, "response");
  }
}

function parseStdout(chunk) {
  stdoutBuffer += chunk.toString("utf8");
  let newlineIndex;
  while ((newlineIndex = stdoutBuffer.indexOf("\n")) >= 0) {
    const line = stdoutBuffer.slice(0, newlineIndex).trim();
    stdoutBuffer = stdoutBuffer.slice(newlineIndex + 1);
    if (!line) {
      continue;
    }
    try {
      handleMessage(JSON.parse(line));
    } catch (error) {
      log("failed to parse app-server stdout", { message: error.message, line: line.slice(0, 300) });
    }
  }
}

function parseStderr(chunk) {
  const lines = chunk.toString("utf8").split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    if (/remote|wham|websocket|Conflict|online|error/i.test(line)) {
      log("app-server stderr", line);
    }
    if (line.includes("Remote app server already online")) {
      conflictSeen = true;
      log("remote conflict detected; another app-server is already online");
      shutdown({ disableRemoteControl: false });
    }
  }
}

function startChild() {
  fs.mkdirSync(codexHome, { recursive: true });
  fs.writeFileSync(pidPath, String(process.pid), "utf8");
  stdoutBuffer = "";
  lastStatus = null;

  log("starting codex app-server", { codexJs });
  child = spawn(process.execPath, [codexJs, "app-server", "--listen", "stdio://"], {
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });

  child.stdout.on("data", parseStdout);
  child.stderr.on("data", parseStderr);
  child.on("exit", (code, signal) => {
    log("app-server exited", { code, signal, lastStatus: statusForLog(lastStatus) });
    child = null;
    if (!shuttingDown) {
      restartChild(5000);
    }
  });

  send("initialize", {
    clientInfo: {
      name: "Codex Desktop",
      title: "Codex Remote Keepalive",
      version: "0.1.0",
    },
    capabilities: {
      experimentalApi: true,
      requestAttestation: false,
      optOutNotificationMethods: [],
    },
  });

  setTimeout(() => notify("initialized"), 200);
  setTimeout(() => send("remoteControl/enable"), 1000);

  pollTimer = setInterval(() => {
    send("remoteControl/status/read");
  }, 30000);
}

function restartChild(delayMs) {
  if (restartTimer || shuttingDown || conflictSeen) {
    return;
  }
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (child) {
    try {
      child.kill();
    } catch {
      // Ignore cleanup races.
    }
  }
  restartTimer = setTimeout(() => {
    restartTimer = null;
    startChild();
  }, delayMs);
}

function shutdown({ disableRemoteControl = true } = {}) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  log("shutdown requested", { disableRemoteControl });
  if (pollTimer) {
    clearInterval(pollTimer);
  }
  if (restartTimer) {
    clearTimeout(restartTimer);
  }
  if (child) {
    if (disableRemoteControl) {
      send("remoteControl/disable");
    }
    setTimeout(() => {
      try {
        child.kill();
      } catch {
        // Ignore cleanup races.
      }
      process.exit(0);
    }, 800);
  } else {
    process.exit(0);
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
process.on("exit", () => {
  try {
    fs.rmSync(pidPath, { force: true });
  } catch {
    // Ignore cleanup races.
  }
});
process.on("uncaughtException", (error) => {
  log("uncaught exception", { message: error.message, stack: error.stack });
  shutdown();
});

startChild();
