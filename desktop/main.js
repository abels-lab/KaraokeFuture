const { app, BrowserWindow, screen, session, shell, ipcMain } = require("electron");
const http = require("http");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

// 1. Automatically enable Chromium flags before app.whenReady()
// Allows WebAudio / video playback immediately without requiring prior user gestures.
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");

const PORT = parseInt(process.env.KARAOKE_PORT || "8010", 10);
const HOST = process.env.KARAOKE_HOST || "localhost";
const BASE_URL = `http://${HOST}:${PORT}`;

let tvWindow = null;
let projectorWindow = null;
let backendProcess = null;

/**
 * Check if the Python backend is already responding on the configured port.
 */
function checkBackendReady() {
  return new Promise((resolve) => {
    const req = http.get(`${BASE_URL}/api/info`, { timeout: 1500 }, (res) => {
      if (res.statusCode >= 200 && res.statusCode < 400) {
        res.resume();
        resolve(true);
      } else {
        res.resume();
        resolve(false);
      }
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

/**
 * Poll until backend is online.
 */
async function waitForBackend(maxAttempts = 60, intervalMs = 500) {
  for (let i = 0; i < maxAttempts; i++) {
    const ready = await checkBackendReady();
    if (ready) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

/**
 * Spawns the Python backend process if not already running.
 */
function spawnBackend() {
  const venvPython = path.resolve(__dirname, "../ai_karaoke/.venv/Scripts/python.exe");
  const pythonExe = fs.existsSync(venvPython) ? venvPython : "python";
  const cwd = path.resolve(__dirname, "../ai_karaoke");

  console.log(`[Desktop] Spawning Python backend via ${pythonExe} in ${cwd}...`);
  backendProcess = spawn(pythonExe, ["main.py"], {
    cwd,
    env: {
      ...process.env,
      KARAOKE_PORT: String(PORT),
      PYTHONUNBUFFERED: "1"
    },
    windowsHide: true,
    stdio: "inherit"
  });

  backendProcess.on("error", (err) => {
    console.error("[Desktop] Error launching Python backend:", err);
  });

  backendProcess.on("exit", (code, signal) => {
    console.log(`[Desktop] Python backend exited (code=${code}, signal=${signal})`);
  });
}

/**
 * Cleanly terminates the Python backend child process.
 */
function killBackend() {
  if (backendProcess && !backendProcess.killed) {
    console.log("[Desktop] Terminating Python backend...");
    try {
      if (process.platform === "win32") {
        spawn("taskkill", ["/pid", backendProcess.pid.toString(), "/f", "/t"]);
      } else {
        backendProcess.kill("SIGTERM");
      }
    } catch (e) {
      console.error("[Desktop] Error terminating backend:", e);
    }
    backendProcess = null;
  }
}

/**
 * Smart Multi-Monitor Projector Handling:
 * Detects whether a secondary monitor or projector is attached.
 * If yes: opens fullscreen on that display.
 * If no: opens movable 1280x720 window with F11 / Alt+Enter toggle.
 */
function openProjectorWindow() {
  if (projectorWindow && !projectorWindow.isDestroyed()) {
    projectorWindow.focus();
    return projectorWindow;
  }

  const allDisplays = screen.getAllDisplays();
  const primaryDisplay = screen.getPrimaryDisplay();

  let tvDisplay = primaryDisplay;
  if (tvWindow && !tvWindow.isDestroyed()) {
    tvDisplay = screen.getDisplayMatching(tvWindow.getBounds());
  }

  // Detect external display (different from the display hosting the control panel)
  const projectorDisplay = allDisplays.find((d) => d.id !== tvDisplay.id) ||
    allDisplays.find((d) => d.id !== primaryDisplay.id);

  let windowOptions;
  if (projectorDisplay) {
    // External display / projector detected -> fullscreen on that display
    windowOptions = {
      x: projectorDisplay.bounds.x,
      y: projectorDisplay.bounds.y,
      width: projectorDisplay.bounds.width,
      height: projectorDisplay.bounds.height,
      fullscreen: true,
      backgroundColor: "#0c0a09",
      autoHideMenuBar: true,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false
      }
    };
  } else {
    // Single display -> movable 1280x720 window
    windowOptions = {
      width: 1280,
      height: 720,
      minWidth: 800,
      minHeight: 450,
      backgroundColor: "#0c0a09",
      autoHideMenuBar: true,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false
      }
    };
  }

  projectorWindow = new BrowserWindow(windowOptions);

  // F11 / Alt+Enter fullscreen toggle support
  projectorWindow.webContents.on("before-input-event", (event, input) => {
    if (
      (input.key === "F11" && input.type === "keyDown") ||
      (input.key === "Enter" && input.alt && input.type === "keyDown")
    ) {
      projectorWindow.setFullScreen(!projectorWindow.isFullScreen());
      event.preventDefault();
    }
  });

  // Open external links in default system browser
  projectorWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http:") || url.startsWith("https:")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  projectorWindow.loadURL(`${BASE_URL}/screen`);

  projectorWindow.on("closed", () => {
    projectorWindow = null;
  });

  return projectorWindow;
}

/**
 * Creates the Control Panel Window (/tv)
 */
function createTvWindow() {
  tvWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: "#0c0a09",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // Intercept window.open calls from the Control Panel
  tvWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Intercept clicking Screen (/screen)
    if (url.includes("/screen")) {
      openProjectorWindow();
      return { action: "deny" };
    }
    // Open external links (like Buy me a coffee or documentation) in system browser
    if (url.startsWith("http:") || url.startsWith("https:")) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "deny" };
  });

  // Keyboard shortcut F11 for Control Panel
  tvWindow.webContents.on("before-input-event", (event, input) => {
    if (input.key === "F11" && input.type === "keyDown") {
      tvWindow.setFullScreen(!tvWindow.isFullScreen());
      event.preventDefault();
    }
  });

  tvWindow.loadURL(`${BASE_URL}/tv`);

  tvWindow.on("closed", () => {
    tvWindow = null;
  });
}

// App lifecycle
app.whenReady().then(async () => {
  // Auto-grant microphone ("media") permissions for seamless pitch scoring
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    if (permission === "media") {
      return callback(true);
    }
    callback(false);
  });

  // Spawn backend if not already running
  const isRunning = await checkBackendReady();
  if (!isRunning) {
    spawnBackend();
  }

  const ready = await waitForBackend();
  if (!ready) {
    console.warn("[Desktop] Backend did not respond within timeout, opening UI anyway...");
  }

  createTvWindow();
});

// IPC handlers matching preload.js
ipcMain.handle("open-projector", () => {
  openProjectorWindow();
});

ipcMain.handle("toggle-fullscreen", (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win) {
    win.setFullScreen(!win.isFullScreen());
  }
});

app.on("window-all-closed", () => {
  killBackend();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", killBackend);
app.on("will-quit", killBackend);
process.on("exit", killBackend);
process.on("SIGINT", () => {
  killBackend();
  process.exit(0);
});
process.on("SIGTERM", () => {
  killBackend();
  process.exit(0);
});
