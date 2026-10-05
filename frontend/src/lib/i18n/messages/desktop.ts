import type { Messages } from "../core";

export const desktop = {
  "server.title": { en: "Server", de: "Server" },
  "server.info": {
    en: "Where NotFlix's backend runs for this app.",
    de: "Wo das NotFlix-Backend für diese App läuft.",
  },
  "server.builtIn": { en: "This PC (built-in)", de: "Dieser PC (eingebaut)" },
  "server.remote": { en: "Another server", de: "Anderer Server" },
  "server.builtInInfo": {
    en: "NotFlix runs completely on this PC: database, sources and everything else start with the app. To sign in, create an API client at MyAnimeList and/or AniList and enter it here.",
    de: "NotFlix läuft komplett auf diesem PC: Datenbank, Quellen und alles andere starten mit der App. Zum Anmelden lege bei MyAnimeList und/oder AniList einen API-Client an und trage ihn hier ein.",
  },
  "server.builtInError": {
    en: "The built-in server didn't start: {error}",
    de: "Der eingebaute Server ist nicht gestartet: {error}",
  },
  "server.malClientId": { en: "MyAnimeList client ID", de: "MyAnimeList-Client-ID" },
  "server.malClientSecret": { en: "MyAnimeList client secret", de: "MyAnimeList-Client-Secret" },
  "server.anilistClientId": { en: "AniList client ID", de: "AniList-Client-ID" },
  "server.anilistClientSecret": { en: "AniList client secret", de: "AniList-Client-Secret" },
  "server.redirects": {
    en: "Redirect URLs to register there:",
    de: "Dort einzutragende Redirect-URLs:",
  },
  "server.aniworldVia": { en: "AniWorld through", de: "AniWorld über" },
  "server.viaAniScraper": {
    en: "AniScraper (direct streams where possible)",
    de: "AniScraper (wo möglich direkte Streams)",
  },
  "server.viaSerienStream": {
    en: "SerienStreamAPI (hoster players)",
    de: "SerienStreamAPI (Player der Hoster)",
  },
  "server.saveRestart": { en: "Save and restart", de: "Speichern und neu starten" },
  "server.restarting": { en: "Restarting…", de: "Starte neu…" },
  "server.logs": { en: "Open logs", de: "Logs öffnen" },
  "server.address": { en: "Backend address", de: "Backend-Adresse" },
  "server.key": { en: "API key", de: "API-Schlüssel" },
  "server.keySaved": {
    en: "Saved (leave empty to keep it)",
    de: "Gespeichert (leer lassen, um ihn zu behalten)",
  },
  "server.connect": { en: "Connect", de: "Verbinden" },
  "server.checking": { en: "Connecting…", de: "Verbinde…" },
  "server.missing": {
    en: "Enter the address of your NotFlix server to get started.",
    de: "Gib die Adresse deines NotFlix-Servers ein, um loszulegen.",
  },
  "server.unreachable": {
    en: "The server at {url} can't be reached or doesn't accept the API key.",
    de: "Der Server unter {url} ist nicht erreichbar oder akzeptiert den API-Schlüssel nicht.",
  },
  "server.hint": {
    en: "The address is either the backend itself (e.g. http://my-server:8000) or the web app's address followed by /api (e.g. https://notflix.example.com/api). The key is the server's API_KEY; it stays in this app.",
    de: "Die Adresse ist entweder das Backend selbst (z. B. http://mein-server:8000) oder die Adresse der Web-App mit /api dahinter (z. B. https://notflix.example.com/api). Der Schlüssel ist der API_KEY des Servers; er bleibt in dieser App.",
  },
  "server.error.invalid": {
    en: "That isn't an http:// or https:// address.",
    de: "Das ist keine http://- oder https://-Adresse.",
  },
  "server.error.unreachable": {
    en: "No answer from that address.",
    de: "Keine Antwort von dieser Adresse.",
  },
  "server.error.wrongKey": {
    en: "The server doesn't accept this API key.",
    de: "Der Server akzeptiert diesen API-Schlüssel nicht.",
  },
  "server.error.missingKey": {
    en: "Enter the server's API key.",
    de: "Gib den API-Schlüssel des Servers ein.",
  },
  "server.error.builtInFailed": {
    en: "The built-in server didn't start: see its logs.",
    de: "Der eingebaute Server ist nicht gestartet: siehe Logs.",
  },
  "server.error.notNotflix": {
    en: "Something answers there, but it isn't a NotFlix backend.",
    de: "Dort antwortet etwas, aber kein NotFlix-Backend.",
  },
} satisfies Messages;
