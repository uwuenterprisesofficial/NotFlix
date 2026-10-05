// NotFlix desktop app.
//
// The app runs the web frontend's own server (the Next.js standalone build in server/) on this
// PC and shows it in a window. That server passes /api/* on to the NotFlix backend chosen in the
// app's settings, which can run anywhere (e.g. on a home server). The backend's address is kept
// in config.json in the app's data folder; changing it restarts the local server.

const { app, BrowserWindow, Menu, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

// A fixed port keeps the app's origin, and so its local storage (player settings, resume
// points), the same between runs. The next few are tried when it's taken.
const PORTS = Array.from({ length: 10 }, (_, i) => 47300 + i);
// Before a backend is chosen the server still starts (showing the server settings); requests
// to the backend then fail at once.
const NO_BACKEND = "http://127.0.0.1:1";
// Sites the window may show for signing in (everything else opens in the browser).
const SIGN_IN_HOSTS = ["myanimelist.net", "anilist.co"];
const START_TIMEOUT_MS = 30_000;
const CHECK_TIMEOUT_MS = 8_000;

const serverDir = app.isPackaged
  ? path.join(process.resourcesPath, "server")
  : path.join(__dirname, "server");

let win = null;
let server = null;
let origin = null; // the local server, e.g. http://127.0.0.1:47300
// Where the backend's sign-in callbacks land (its web app), learnt from the backend.
let publicOrigin = null;

// --- Settings ---

function configPath() {
  return path.join(app.getPath("userData"), "config.json");
}

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(configPath(), "utf8"));
  } catch {
    return {};
  }
}

function writeConfig(config) {
  fs.mkdirSync(path.dirname(configPath()), { recursive: true });
  fs.writeFileSync(configPath(), JSON.stringify(config, null, 2));
}

/** An http(s) address without a trailing slash, or null. */
function normalize(raw) {
  let url;
  try {
    url = new URL(String(raw).trim());
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  url.search = "";
  url.hash = "";
  return url.toString().replace(/\/+$/, "");
}

/** Whether a NotFlix backend answers at `url`: "ok", "unreachable" or "notNotflix". */
async function check(url) {
  let res;
  try {
    res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(CHECK_TIMEOUT_MS) });
  } catch {
    return "unreachable";
  }
  const body = await res.json().catch(() => null);
  return res.ok && body?.status === "ok" ? "ok" : "notNotflix";
}

/** The backend's web app (its FRONTEND_URL): sign-ins come back through it. */
async function learnPublicOrigin(backend) {
  publicOrigin = null;
  if (!backend) return;
  try {
    const res = await fetch(`${backend}/auth/providers`, {
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
    });
    const body = await res.json();
    if (body?.public_url) publicOrigin = new URL(body.public_url).origin;
  } catch {
    // Unknown: sign-in pages are still allowed (see allowedInWindow).
  }
}

// --- The local server ---

function portFree(port) {
  return new Promise((resolve) => {
    const probe = net.createServer();
    probe.once("error", () => resolve(false));
    probe.listen(port, "127.0.0.1", () => probe.close(() => resolve(true)));
  });
}

async function choosePort(preferred) {
  for (const port of [preferred, ...PORTS]) {
    if (port && (await portFree(port))) return port;
  }
  throw new Error(`None of the ports ${PORTS[0]}-${PORTS.at(-1)} is free`);
}

async function waitUntilUp(url, child) {
  const deadline = Date.now() + START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`The server stopped (exit ${child.exitCode})`);
    try {
      await fetch(`${url}/favicon.ico`, { signal: AbortSignal.timeout(1000) });
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
  }
  throw new Error("The server didn't start in time");
}

async function startServer() {
  const config = readConfig();
  const port = await choosePort(config.port);
  if (port !== config.port) writeConfig({ ...config, port });
  const log = fs.createWriteStream(path.join(app.getPath("userData"), "server.log"));
  // Electron's own binary runs the server as plain Node.js.
  const child = spawn(process.execPath, [path.join(serverDir, "server.js")], {
    cwd: serverDir,
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: "1",
      NODE_ENV: "production",
      NEXT_TELEMETRY_DISABLED: "1",
      HOSTNAME: "127.0.0.1",
      PORT: String(port),
      NOTFLIX_DESKTOP: "1",
      API_INTERNAL_URL: config.backend || NO_BACKEND,
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  server = child;
  origin = `http://127.0.0.1:${port}`;
  await Promise.all([waitUntilUp(origin, child), learnPublicOrigin(config.backend)]);
}

function stopServer() {
  const child = server;
  server = null;
  if (!child || child.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    child.once("exit", resolve);
    child.kill();
  });
}

// --- The window ---

function isApp(url) {
  try {
    return new URL(url).origin === origin;
  } catch {
    return false;
  }
}

/** Sign-in pages stay in the window (the sign-in must come back to it); the rest doesn't. */
function allowedInWindow(url) {
  let target;
  try {
    target = new URL(url);
  } catch {
    return false;
  }
  if (target.origin === origin || target.origin === publicOrigin) return true;
  const backend = readConfig().backend;
  if (backend && target.origin === new URL(backend).origin) return true;
  return SIGN_IN_HOSTS.some((h) => target.hostname === h || target.hostname.endsWith(`.${h}`));
}

function openOutside(url) {
  if (/^https?:\/\//.test(url)) void shell.openExternal(url);
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 800,
    minHeight: 500,
    backgroundColor: "#141414",
    title: "NotFlix",
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  win.once("ready-to-show", () => win.show());
  win.on("closed", () => (win = null));

  win.webContents.on("will-navigate", (event) => {
    if (allowedInWindow(event.url)) return;
    // While signing in, the provider's own pages go where they need to.
    if (!isApp(win.webContents.getURL())) return;
    event.preventDefault();
    // Links in the app open in the browser; a video embed trying to take over the window
    // (ads) is just stopped.
    if (!event.initiator || event.initiator === win.webContents.mainFrame) openOutside(event.url);
  });
  win.webContents.setWindowOpenHandler(({ url, referrer }) => {
    if (isApp(referrer?.url ?? "")) openOutside(url); // embeds' pop-ups are dropped
    return { action: "deny" };
  });

  const start = readConfig().backend ? "/" : "/login";
  void win.loadURL(`${origin}${start}`);
}

ipcMain.handle("backend:get", () => readConfig().backend ?? null);

ipcMain.handle("backend:set", async (event, raw) => {
  if (!isApp(event.senderFrame?.url ?? "")) return { ok: false, error: "invalid" };
  const backend = normalize(raw);
  if (!backend) return { ok: false, error: "invalid" };
  const status = await check(backend);
  if (status !== "ok") return { ok: false, error: status };
  writeConfig({ ...readConfig(), backend });
  await stopServer();
  await startServer();
  // Signed in at another backend (or not at all): start over.
  void win?.loadURL(`${origin}/`);
  return { ok: true };
});

function buildMenu() {
  const serverSettings = {
    label: "Server settings…",
    click: () => win?.loadURL(`${origin}/settings#server`),
  };
  const template = [
    ...(process.platform === "darwin"
      ? [
          {
            label: app.name,
            submenu: [
              { role: "about" },
              { type: "separator" },
              serverSettings,
              { type: "separator" },
              { role: "hide" },
              { role: "quit" },
            ],
          },
        ]
      : [{ label: "File", submenu: [serverSettings, { type: "separator" }, { role: "quit" }] }]),
    { role: "editMenu" },
    {
      label: "View",
      submenu: [
        {
          label: "Back",
          accelerator: process.platform === "darwin" ? "Cmd+[" : "Alt+Left",
          click: () => win?.webContents.navigationHistory.goBack(),
        },
        {
          label: "Forward",
          accelerator: process.platform === "darwin" ? "Cmd+]" : "Alt+Right",
          click: () => win?.webContents.navigationHistory.goForward(),
        },
        { type: "separator" },
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// Episodes start by themselves (autoplay, the next episode, Watch Together).
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    win.focus();
  });

  app.whenReady().then(async () => {
    buildMenu();
    try {
      await startServer();
    } catch (error) {
      const { dialog } = require("electron");
      dialog.showErrorBox("NotFlix couldn't start", String(error?.message ?? error));
      app.quit();
      return;
    }
    createWindow();
    app.on("activate", () => {
      if (!win) createWindow();
    });
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  let stopping = false;
  app.on("before-quit", (event) => {
    if (stopping || !server) return;
    stopping = true;
    event.preventDefault();
    void stopServer().finally(() => app.quit());
  });
}
