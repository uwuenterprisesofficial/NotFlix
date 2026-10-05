import type { Messages } from "../core";

export const desktop = {
  "server.title": { en: "Server", de: "Server" },
  "server.info": {
    en: "The NotFlix backend this app connects to.",
    de: "Das NotFlix-Backend, mit dem sich diese App verbindet.",
  },
  "server.address": { en: "Backend address", de: "Backend-Adresse" },
  "server.connect": { en: "Connect", de: "Verbinden" },
  "server.checking": { en: "Connecting…", de: "Verbinde…" },
  "server.missing": {
    en: "Enter the address of your NotFlix server to get started.",
    de: "Gib die Adresse deines NotFlix-Servers ein, um loszulegen.",
  },
  "server.unreachable": {
    en: "The server at {url} can't be reached.",
    de: "Der Server unter {url} ist nicht erreichbar.",
  },
  "server.hint": {
    en: "Either the backend itself (e.g. http://my-server:8000) or the web app's address followed by /api (e.g. https://notflix.example.com/api).",
    de: "Entweder das Backend selbst (z. B. http://mein-server:8000) oder die Adresse der Web-App mit /api dahinter (z. B. https://notflix.example.com/api).",
  },
  "server.error.invalid": {
    en: "That isn't an http:// or https:// address.",
    de: "Das ist keine http://- oder https://-Adresse.",
  },
  "server.error.unreachable": {
    en: "No answer from that address.",
    de: "Keine Antwort von dieser Adresse.",
  },
  "server.error.notNotflix": {
    en: "Something answers there, but it isn't a NotFlix backend.",
    de: "Dort antwortet etwas, aber kein NotFlix-Backend.",
  },
} satisfies Messages;
