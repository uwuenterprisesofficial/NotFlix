// The bridge between the app's pages and the desktop app (see frontend/src/lib/desktop.ts).
// Only the app's own pages get it (not MyAnimeList's or AniList's sign-in pages, which load in
// the same window); the main process checks the sender again.
const { contextBridge, ipcRenderer } = require("electron");

if (location.protocol === "http:" && location.hostname === "127.0.0.1") {
  contextBridge.exposeInMainWorld("notflixDesktop", {
    backend: () => ipcRenderer.invoke("backend:get"),
    setBackend: (url) => ipcRenderer.invoke("backend:set", String(url)),
  });
}
