// Updates of the desktop app, from the NotFlix server it's connected to: the server's image
// carries the app's latest release (backend/app/api/updates.py, filled by scripts/publish.sh),
// so updating the server updates the app. electron-updater's "generic" provider asks the
// server for latest.yml (latest-linux.yml, latest-mac.yml) with the API key.
//
// Checked at start and every few hours, downloaded in the background, and installed when the
// app quits; once it's ready the window is told (it shows "Restart to update"), and a system
// notification says so while the window isn't focused.

const { Notification, app } = require("electron");

const CHECK_EVERY_MS = 4 * 3600 * 1000;
const FIRST_CHECK_DELAY_MS = 10_000; // after the app has started

let updater = null; // electron-updater's autoUpdater (loaded only in a packaged app)
let timer = null;
let feed = null;
let status = { state: "idle", version: null, progress: null, error: null };
let onStatus = () => {};

/** Whether this build can update itself (not while developing, not the portable .exe). */
function supported() {
  return app.isPackaged && !process.env.PORTABLE_EXECUTABLE_DIR;
}

function setStatus(next) {
  status = { ...status, ...next };
  onStatus(status);
}

function load() {
  if (updater) return updater;
  ({ autoUpdater: updater } = require("electron-updater"));
  updater.autoDownload = true;
  updater.autoInstallOnAppQuit = true;
  updater.allowDowngrade = false;
  updater.logger = null;
  updater.on("checking-for-update", () => setStatus({ state: "checking", error: null }));
  updater.on("update-not-available", () => setStatus({ state: "upToDate" }));
  updater.on("update-available", (info) =>
    setStatus({ state: "downloading", version: info.version, progress: 0 }),
  );
  updater.on("download-progress", (p) => setStatus({ progress: Math.round(p.percent) }));
  updater.on("update-downloaded", (info) => {
    setStatus({ state: "ready", version: info.version, progress: 100 });
    notify(info.version);
  });
  updater.on("error", (error) =>
    setStatus({ state: "error", error: String(error?.message ?? error).slice(0, 300) }),
  );
  return updater;
}

let notified = null;
function notify(version) {
  if (notified === version || !Notification.isSupported()) return;
  notified = version;
  const shown = new Notification({
    title: "NotFlix update ready",
    body: `Version ${version} is downloaded. Restart NotFlix to use it.`,
  });
  shown.on("click", () => install());
  shown.show();
}

async function check() {
  if (!feed || !supported()) return status;
  try {
    await load().checkForUpdates();
  } catch (error) {
    setStatus({ state: "error", error: String(error?.message ?? error).slice(0, 300) });
  }
  return status;
}

/**
 * Updates from the server at `url` (with its API key), or none (`url` null: the built-in
 * server alone has no releases to hand out). Called whenever the app (re)starts its backend.
 */
function configure(url, key, listener) {
  onStatus = listener ?? onStatus;
  clearInterval(timer);
  timer = null;
  feed = url ? { url: `${url.replace(/\/+$/, "")}/updates`, key } : null;
  if (!feed || !supported()) {
    setStatus({ state: supported() ? "noServer" : "unsupported" });
    return;
  }
  const u = load();
  u.setFeedURL({ provider: "generic", url: feed.url });
  u.requestHeaders = { "x-api-key": feed.key };
  setTimeout(() => void check(), FIRST_CHECK_DELAY_MS);
  timer = setInterval(() => void check(), CHECK_EVERY_MS);
}

/** Restart into the downloaded update. */
function install() {
  if (status.state !== "ready" || !updater) return false;
  // (the app's before-quit stops the servers; then the installer runs)
  setImmediate(() => updater.quitAndInstall(true, true));
  return true;
}

module.exports = { configure, check, install, status: () => status, supported };
