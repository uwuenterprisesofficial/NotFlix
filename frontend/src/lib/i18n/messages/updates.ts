import type { Messages } from "../core";

export const updates = {
  "changelog.title": { en: "Changelog", de: "Änderungsprotokoll" },
  "changelog.version": { en: "Version {version}", de: "Version {version}" },
  "changelog.whatsNew": { en: "What’s new", de: "Was ist neu" },
  "changelog.updated": {
    en: "Updated to version {version}",
    de: "Aktualisiert auf Version {version}",
  },
  "changelog.all": { en: "All changes", de: "Alle Änderungen" },
  "changelog.continue": { en: "Let’s go", de: "Los geht’s" },

  "update.title": { en: "App version", de: "App-Version" },
  "update.current": { en: "NotFlix {version}", de: "NotFlix {version}" },
  "update.ready": {
    en: "Update {version} is ready",
    de: "Update {version} ist bereit",
  },
  "update.restartInfo": {
    en: "Restart NotFlix to use it (or it’s installed when you close it).",
    de: "Starte NotFlix neu, um es zu nutzen (sonst wird es beim Schließen installiert).",
  },
  "update.restart": { en: "Restart now", de: "Jetzt neu starten" },
  "update.later": { en: "Later", de: "Später" },
  "update.check": { en: "Check for updates", de: "Nach Updates suchen" },
  "update.checking": { en: "checking for updates…", de: "suche nach Updates…" },
  "update.upToDate": { en: "up to date", de: "aktuell" },
  "update.downloading": {
    en: "downloading {version} ({progress}%)…",
    de: "lade {version} herunter ({progress} %)…",
  },
  "update.failed": { en: "the update check failed", de: "die Update-Suche ist fehlgeschlagen" },
  "update.noServer": {
    en: "updates come from a NotFlix server: connect to one in the server settings",
    de: "Updates kommen von einem NotFlix-Server: verbinde dich in den Servereinstellungen mit einem",
  },
  "update.unsupported": {
    en: "this build doesn’t update itself (development or portable version)",
    de: "diese Version aktualisiert sich nicht selbst (Entwicklungs- oder portable Version)",
  },
} satisfies Messages;
