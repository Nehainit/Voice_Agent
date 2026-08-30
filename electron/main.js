const { app, BrowserWindow, clipboard, dialog, globalShortcut, ipcMain, screen, session } = require("electron");
const { execFile } = require("node:child_process");
const path = require("node:path");

const SERVICE_URL = process.env.CODEDUCK_SERVICE_URL || "http://127.0.0.1:8765";
const AGENT_NAME = process.env.CODEDUCK_AGENT_NAME || "Neha";
const SHORTCUT_CANDIDATES = [
  process.env.CODEDUCK_SHORTCUT,
  "CommandOrControl+Alt+K",
  "CommandOrControl+Alt+L",
].filter(Boolean);

let mainWindow;
let bubbleWindow;
let lastClipboardText = "";
let activeShortcut = SHORTCUT_CANDIDATES[0];
let lastPresence = { state: "idle", status: "Ready", context: "Click to open Neha" };

function createMainWindow() {
  const area = activeWorkArea();
  mainWindow = new BrowserWindow({
    width: 1120,
    height: 760,
    minWidth: 940,
    minHeight: 640,
    x: area.x + Math.max(24, Math.round((area.width - 1120) / 2)),
    y: area.y + Math.max(32, Math.round((area.height - 760) / 2)),
    frame: true,
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    backgroundColor: "#fbf8f0",
    resizable: true,
    maximizable: true,
    fullscreenable: true,
    alwaysOnTop: false,
    visibleOnAllWorkspaces: false,
    skipTaskbar: false,
    show: false,
    title: AGENT_NAME,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.once("ready-to-show", showMainWindow);
  mainWindow.webContents.once("did-finish-load", showMainWindow);
  mainWindow.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription) => {
    console.error(`Neha renderer failed to load: ${errorCode} ${errorDescription}`);
  });
}

function createBubbleWindow() {
  const area = activeWorkArea();
  bubbleWindow = new BrowserWindow({
    width: 68,
    height: 68,
    x: area.x + Math.max(16, area.width - 92),
    y: area.y + Math.max(16, area.height - 112),
    frame: false,
    transparent: true,
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    visibleOnAllWorkspaces: true,
    skipTaskbar: true,
    show: false,
    title: `${AGENT_NAME} Bubble`,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  bubbleWindow.setAlwaysOnTop(true, "screen-saver");
  bubbleWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  bubbleWindow.loadFile(path.join(__dirname, "renderer", "bubble.html"));
  bubbleWindow.once("ready-to-show", () => {
    if (!bubbleWindow || bubbleWindow.isDestroyed()) return;
    bubbleWindow.showInactive();
    bubbleWindow.webContents.send("presence:updated", lastPresence);
  });
  bubbleWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription) => {
    console.error(`Neha bubble failed to load: ${errorCode} ${errorDescription}`);
  });
}

app.whenReady().then(() => {
  console.log(`Neha desktop starting. Service: ${SERVICE_URL}.`);
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    callback(permission === "media");
  });
  createMainWindow();
  createBubbleWindow();
  registerShortcut();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  app.isQuitting = true;
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

ipcMain.handle("app:getConfig", () => ({
  serviceUrl: SERVICE_URL,
  shortcut: activeShortcut,
  agentName: AGENT_NAME,
  platform: process.platform,
}));

ipcMain.handle("selection:capture", async () => {
  return captureSelection({ hideWindow: true });
});

async function captureSelection({ hideWindow }) {
  if (hideWindow && mainWindow) {
    mainWindow.hide();
    await delay(120);
  }
  lastClipboardText = clipboard.readText();
  const activeWindow = await getActiveWindowInfo();
  await sendCopyShortcut();
  await delay(180);
  const selectedText = clipboard.readText();
  if (lastClipboardText !== selectedText) {
    clipboard.writeText(lastClipboardText);
  }
  if (hideWindow && mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  }
  return {
    selectedText,
    source: "clipboard",
    activeApp: activeWindow.activeApp,
    windowTitle: activeWindow.windowTitle,
    ...inferFileInfo(activeWindow.windowTitle),
  };
}

ipcMain.handle("project:chooseRoot", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose project folder",
    properties: ["openDirectory"],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return { canceled: true, projectRoot: "" };
  }
  return { canceled: false, projectRoot: result.filePaths[0] };
});

ipcMain.handle("patch:applyReplacement", async (_event, proposedCode) => {
  if (!proposedCode || typeof proposedCode !== "string") {
    return { ok: false, message: "No replacement code was provided." };
  }

  const previousClipboard = clipboard.readText();
  clipboard.writeText(proposedCode);
  if (mainWindow) mainWindow.hide();
  await delay(160);
  await sendPasteShortcut();
  await delay(250);
  clipboard.writeText(previousClipboard);
  if (mainWindow) mainWindow.showInactive();
  return { ok: true, message: "Replacement pasted into the active selection." };
});

ipcMain.handle("clipboard:writeText", (_event, text) => {
  clipboard.writeText(String(text || ""));
  return { ok: true };
});

ipcMain.handle("clipboard:pasteText", async (_event, text) => {
  const value = String(text || "");
  if (!value) {
    return { ok: false, message: "No text was provided to paste." };
  }
  const previousClipboard = clipboard.readText();
  clipboard.writeText(value);
  if (mainWindow) mainWindow.hide();
  try {
    await delay(160);
    await sendPasteShortcut();
    await delay(220);
    return { ok: true, message: "Dictation pasted into the focused app." };
  } catch (error) {
    return { ok: false, message: error.message || String(error) };
  } finally {
    clipboard.writeText(previousClipboard);
    if (mainWindow) mainWindow.showInactive();
  }
});

ipcMain.handle("window:resize", (_event, size) => {
  if (!mainWindow) return;
  const width = Number(size && size.width) || 1120;
  const height = Number(size && size.height) || 760;
  mainWindow.setSize(Math.min(Math.max(width, 940), 1600), Math.min(Math.max(height, 640), 1100), true);
});

ipcMain.handle("window:closePanel", () => {
  if (mainWindow) mainWindow.hide();
});

ipcMain.handle("window:quitApp", () => {
  app.isQuitting = true;
  app.quit();
  return { ok: true };
});

ipcMain.handle("window:openMain", () => {
  showMainWindow();
  return { ok: true };
});

ipcMain.handle("presence:update", (_event, presence) => {
  lastPresence = { ...lastPresence, ...(presence || {}) };
  if (bubbleWindow && !bubbleWindow.isDestroyed()) {
    bubbleWindow.webContents.send("presence:updated", lastPresence);
  }
  return { ok: true };
});

function activeWorkArea() {
  const cursor = screen.getCursorScreenPoint();
  return screen.getDisplayNearestPoint(cursor).workArea;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.show();
  mainWindow.focus();
  console.log("Neha desktop ready.");
}

function registerShortcut() {
  for (const shortcut of SHORTCUT_CANDIDATES) {
    const registered = globalShortcut.register(shortcut, async () => {
      if (!mainWindow) return;
      const context = await captureSelection({ hideWindow: false });
      showMainWindow();
      mainWindow.webContents.send("shortcut:triggered", context);
    });
    if (registered) {
      activeShortcut = shortcut;
      console.log(`Neha shortcut registered: ${shortcut}`);
      return;
    }
  }
  console.error(`Neha could not register any shortcut: ${SHORTCUT_CANDIDATES.join(", ")}`);
}

async function sendCopyShortcut() {
  return sendShortcut("copy");
}

async function sendPasteShortcut() {
  return sendShortcut("paste");
}

function sendShortcut(kind) {
  if (process.platform === "darwin") {
    const key = kind === "paste" ? "v" : "c";
    return execFilePromise("osascript", [
      "-e",
      `tell application "System Events" to keystroke "${key}" using command down`,
    ]).catch((error) => {
      throw new Error(`macOS Accessibility permission is required for ${kind}: ${error.message}`);
    });
  }

  if (process.platform === "win32") {
    const key = kind === "paste" ? "^v" : "^c";
    return execFilePromise("powershell.exe", [
      "-NoProfile",
      "-Command",
      `Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('${key}')`,
    ]);
  }

  const key = kind === "paste" ? "ctrl+v" : "ctrl+c";
  return execFilePromise("xdotool", ["key", key]);
}

async function getActiveWindowInfo() {
  if (process.platform === "darwin") {
    try {
      const script = [
        'tell application "System Events"',
        'set frontApp to first application process whose frontmost is true',
        'set appName to name of frontApp',
        'set windowTitle to ""',
        'try',
        'set windowTitle to name of front window of frontApp',
        'end try',
        'return appName & "\\n" & windowTitle',
        "end tell",
      ].join("\n");
      const output = await execFilePromise("osascript", ["-e", script]);
      const [activeApp = "", windowTitle = ""] = output.trim().split("\n");
      return { activeApp, windowTitle };
    } catch {
      return { activeApp: "", windowTitle: "" };
    }
  }
  return { activeApp: "", windowTitle: "" };
}

function execFilePromise(command, args) {
  return new Promise((resolve, reject) => {
    execFile(command, args, { timeout: 5000 }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr || error.message));
        return;
      }
      resolve(stdout);
    });
  });
}

function inferFileInfo(windowTitle) {
  const title = windowTitle || "";
  const fileMatch = title.match(/([A-Za-z0-9_.-]+\.(py|js|jsx|ts|tsx|json|md|css|html|java|go|rs|cpp|c|h|php|rb))/);
  const fileName = fileMatch ? fileMatch[1] : "";
  return {
    fileName,
    languageId: languageFromFileName(fileName),
  };
}

function languageFromFileName(fileName) {
  const ext = path.extname(fileName).toLowerCase();
  const map = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".json": "json",
    ".md": "markdown",
    ".css": "css",
    ".html": "html",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".php": "php",
    ".rb": "ruby",
  };
  return map[ext] || "";
}
