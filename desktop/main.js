// NotFlix desktop app.
//
// The app runs the web frontend's own server (the Next.js standalone build in server/) on this
// PC and shows it in a window. That server passes /api/* on to a NotFlix backend, adding its API
// key. The backend is either
//   - the built-in server (builtin-server.js): the backend and everything it needs, run on this
//     PC from the bundle the app was built with, or
//   - another server (e.g. on a home server), by its address and API key.
// The choice and its settings are kept in config.json in the app's data folder (secrets
// encrypted with the system's key store where there is one); changing them restarts what runs.

const { app, BrowserWindow, Menu, dialog, ipcMain, safeStorage, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const { BuiltInServer, readEnvFile } = require("./builtin-server");

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
// The built-in server's bundle; null when the app was built without it.
const builtIn = BuiltInServer.find(
  app.isPackaged ? path.join(process.resourcesPath, "stack") : path.join(__dirname, "build", "stack"),
);

let win = null;
let server = null;
let origin = null; // the local server, e.g. http://127.0.0.1:47300
// Where the backend's sign-in callbacks land (its web app), learnt from the backend.
let publicOrigin = null;
let builtInRunning = false;
let builtInError = null; // why the built-in server didn't start

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

/** A secret as stored: encrypted with the system's key store where there is one. */
function seal(value) {
  if (!value) return "";
  return safeStorage.isEncryptionAvailable()
    ? `enc:${safeStorage.encryptString(value).toString("base64")}`
    : value;
}

function unseal(stored) {
  if (!stored) return "";
  if (!stored.startsWith("enc:")) return stored;
  try {
    return safeStorage.decryptString(Buffer.from(stored.slice(4), "base64"));
  } catch {
    return ""; // encrypted by another user or system: enter it again
  }
}

/** The other server's API key. */
function readKey(config) {
  if (config.keyEncrypted) return unseal(`enc:${config.keyEncrypted}`);
  return unseal(config.key);
}

function withKey(config, key) {
  const { key: _plain, keyEncrypted: _encrypted, ...rest } = config;
  return { ...rest, key: seal(key) };
}

/** "builtin" (this PC) or "remote" (another server). */
function mode(config) {
  if (config.mode === "remote" || !builtIn) return "remote";
  return config.mode === "builtin" || !config.backend ? "builtin" : "remote";
}

/** The built-in server's passwords (made on first use) and settings. */
function builtInConfig(config) {
  const current = config.builtIn ?? {};
  if (current.secrets) return current;
  const next = { ...current, secrets: BuiltInServer.secrets() };
  writeConfig({ ...config, builtIn: next });
  return next;
}

/** The built-in server's settings for the page (secrets only as "set or not"). */
function builtInSettings(settings = {}) {
  return {
    malClientId: settings.malClientId ?? "",
    hasMalSecret: !!unseal(settings.malClientSecret),
    anilistClientId: settings.anilistClientId ?? "",
    hasAnilistSecret: !!unseal(settings.anilistClientSecret),
    aniworldVia: settings.aniworldVia === "serienstream" ? "serienstream" : "aniscraper",
  };
}

/** The backend's settings from the app's: sign-in apps, AniWorld source, and server.env. */
function builtInEnv(settings = {}) {
  return {
    MAL_CLIENT_ID: settings.malClientId ?? "",
    MAL_CLIENT_SECRET: unseal(settings.malClientSecret),
    ANILIST_CLIENT_ID: settings.anilistClientId ?? "",
    ANILIST_CLIENT_SECRET: unseal(settings.anilistClientSecret),
    ANIWORLD_VIA:
      settings.aniworldVia === "serienstream" && builtIn?.has("aniworld-api") ? "api" : "aniscraper",
    // Anything else the backend reads (see .env.example), one KEY=value per line.
    ...readEnvFile(path.join(dataDir(), "server.env")),
  };
}

function dataDir() {
  return path.join(app.getPath("userData"), "server");
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

/** Whether a NotFlix backend answers at `url` and takes `key`: "ok", "unreachable",
 * "wrongKey" or "notNotflix". */
async function check(url, key) {
  let res;
  try {
    res = await fetch(`${url}/health`, {
      headers: { "x-api-key": key },
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
    });
  } catch {
    return "unreachable";
  }
  const body = await res.json().catch(() => null);
  if (res.status === 401 && /API key/.test(body?.detail ?? "")) return "wrongKey";
  return res.ok && body?.status === "ok" ? "ok" : "notNotflix";
}

/** The backend's web app (its FRONTEND_URL): sign-ins come back through it. */
async function learnPublicOrigin(backend, key) {
  publicOrigin = null;
  if (!backend) return;
  try {
    const res = await fetch(`${backend}/auth/providers`, {
      headers: { "x-api-key": key },
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

/** Start the backend (built-in, or learn about the other one), then this app's own server. */
async function startAll() {
  let config = readConfig();
  const port = await choosePort(config.port);
  if (port !== config.port) writeConfig((config = { ...config, port }));
  let target = { url: config.backend || NO_BACKEND, key: readKey(config) };
  if (mode(config) === "builtin") {
    const { secrets, settings } = builtInConfig(config);
    try {
      builtInRunning = true;
      target = await builtIn.start({
        dataDir: dataDir(),
        // Sign-ins return through localhost (what MyAnimeList and AniList accept as redirect
        // URLs) and are handed over to this window's 127.0.0.1 (see backend/app/api/auth.py).
        webOrigin: `http://localhost:${port}`,
        secrets,
        env: builtInEnv(settings),
        node: process.execPath, // Electron's own Node.js runs Anivexa
        taken: [port],
      });
      builtInError = null;
    } catch (error) {
      builtInError = String(error?.message ?? error);
      await stopBuiltIn();
      target = { url: NO_BACKEND, key: "" };
    }
  }
  await startServer(port, target);
}

async function stopAll() {
  await stopServer();
  await stopBuiltIn();
}

async function stopBuiltIn() {
  if (!builtInRunning) return;
  builtInRunning = false;
  await builtIn.stop();
}

async function startServer(port, target) {
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
      API_INTERNAL_URL: target.url,
      API_KEY: target.key,
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  server = child;
  origin = `http://127.0.0.1:${port}`;
  await Promise.all([waitUntilUp(origin, child), learnPublicOrigin(target.url, target.key)]);
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
  const config = readConfig();
  if (mode(config) === "remote" && config.backend && target.origin === new URL(config.backend).origin) {
    return true;
  }
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
}

const SPLASH = `data:text/html;charset=utf-8,${encodeURIComponent(
  `<!doctype html><title>NotFlix</title>
  <body style="margin:0;height:100vh;display:grid;place-items:center;background:#141414;color:#aaa;font:16px system-ui">
  <div style="text-align:center"><div style="color:#e50914;font:900 42px system-ui">NOTFLIX</div><p>Starting…</p></div>`,
)}`;

function showSplash() {
  void win?.loadURL(SPLASH);
}

/** The app, once everything runs: the sign-in (and server settings) while there's no backend
 * yet or it failed. */
function showApp(page) {
  const config = readConfig();
  const ready = mode(config) === "builtin" ? !builtInError : !!config.backend;
  void win?.loadURL(`${origin}${page ?? (ready ? "/" : "/login")}`);
}

/** Restart with changed settings: the splash meanwhile, the start page after. */
async function restart() {
  showSplash();
  await stopAll();
  await startAll();
  showApp("/");
}

ipcMain.handle("backend:get", () => {
  const config = readConfig();
  return {
    mode: mode(config),
    url: config.backend ?? null,
    hasKey: readKey(config) !== "",
    builtIn: builtIn && {
      error: builtInError,
      settings: builtInSettings(config.builtIn?.settings),
      serienStream: builtIn.has("aniworld-api"),
    },
  };
});

ipcMain.handle("builtin:set", async (event, raw) => {
  if (!builtIn || !isApp(event.senderFrame?.url ?? "")) return { ok: false, error: "invalid" };
  const config = readConfig();
  const current = builtInConfig(config);
  const old = current.settings ?? {};
  const text = (value) => String(value ?? "").trim();
  // Secrets left empty keep the saved ones.
  const settings = {
    malClientId: text(raw?.malClientId),
    malClientSecret: text(raw?.malClientSecret) ? seal(text(raw.malClientSecret)) : old.malClientSecret,
    anilistClientId: text(raw?.anilistClientId),
    anilistClientSecret: text(raw?.anilistClientSecret)
      ? seal(text(raw.anilistClientSecret))
      : old.anilistClientSecret,
    aniworldVia: raw?.aniworldVia === "serienstream" ? "serienstream" : "aniscraper",
  };
  writeConfig({ ...readConfig(), mode: "builtin", builtIn: { ...current, settings } });
  await restart();
  return builtInError ? { ok: false, error: "builtInFailed" } : { ok: true };
});

ipcMain.handle("builtin:logs", (event) => {
  if (!builtIn || !isApp(event.senderFrame?.url ?? "")) return;
  fs.mkdirSync(path.join(dataDir(), "logs"), { recursive: true });
  void shell.openPath(path.join(dataDir(), "logs"));
});

ipcMain.handle("backend:set", async (event, raw, rawKey) => {
  if (!isApp(event.senderFrame?.url ?? "")) return { ok: false, error: "invalid" };
  const backend = normalize(raw);
  if (!backend) return { ok: false, error: "invalid" };
  const config = readConfig();
  // Left empty: the saved one.
  const key = String(rawKey ?? "").trim() || readKey(config);
  if (!key) return { ok: false, error: "missingKey" };
  const status = await check(backend, key);
  if (status !== "ok") return { ok: false, error: status };
  // Signed in at another backend (or not at all): start over.
  writeConfig(withKey({ ...config, backend, mode: "remote" }, key));
  await restart();
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
    createWindow();
    showSplash();
    try {
      await startAll();
    } catch (error) {
      dialog.showErrorBox("NotFlix couldn't start", String(error?.message ?? error));
      app.quit();
      return;
    }
    showApp();
    app.on("activate", () => {
      if (!win) {
        createWindow();
        showApp();
      }
    });
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  let stopping = false;
  app.on("before-quit", (event) => {
    if (stopping || (!server && !builtInRunning)) return;
    stopping = true;
    event.preventDefault();
    void stopAll().finally(() => app.quit());
  });
}
