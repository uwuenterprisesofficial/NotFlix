// The bridge between the app's pages and the desktop app (see frontend/src/lib/desktop.ts).
// Only the app's own pages get it (not MyAnimeList's or AniList's sign-in pages, which load in
// the same window); the main process checks the sender again.
const { contextBridge, ipcRenderer } = require("electron");

if (location.protocol === "http:" && location.hostname === "127.0.0.1") {
  contextBridge.exposeInMainWorld("notflixDesktop", {
    backend: () => ipcRenderer.invoke("backend:get"),
    setBackend: (url, key, options) =>
      ipcRenderer.invoke(
        "backend:set",
        String(url),
        String(key ?? ""),
        JSON.parse(JSON.stringify(options ?? {})),
      ),
    setBuiltIn: (settings) => ipcRenderer.invoke("builtin:set", JSON.parse(JSON.stringify(settings))),
    openLogs: () => ipcRenderer.invoke("builtin:logs"),
    // The app's version, and whether it's opened for the first time (for the changelog).
    version: () => ipcRenderer.invoke("app:version"),
    changelogSeen: () => ipcRenderer.invoke("app:changelogSeen"),
    // Updates (see updater.js).
    updateStatus: () => ipcRenderer.invoke("update:get"),
    checkForUpdates: () => ipcRenderer.invoke("update:check"),
    installUpdate: () => ipcRenderer.invoke("update:install"),
    onUpdateStatus: (callback) => {
      const listener = (_event, status) => callback(status);
      ipcRenderer.on("update:status", listener);
      return () => ipcRenderer.removeListener("update:status", listener);
    },
  });
}
