// Copies the desktop app's latest build (desktop/dist) into backend/releases, so the backend's
// image serves it for the app's auto-update (see backend/app/api/updates.py). Run by
// publish.sh / publish.ps1 before building the backend; also on its own: node scripts/copy-release.mjs
//
// Copied: electron-updater's latest*.yml and the files they name (installers, AppImage, the
// macOS zip), with their .blockmap files (for downloading only what changed). Without a build
// in desktop/dist, backend/releases is left as it is.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "desktop", "dist");
const releases = path.join(root, "backend", "releases");
const CHANNELS = ["latest.yml", "latest-linux.yml", "latest-mac.yml"];

const found = CHANNELS.filter((name) => fs.existsSync(path.join(dist, name)));
if (found.length === 0) {
  console.log(`No desktop build in ${dist} (npm run dist in desktop/): the image keeps what's in backend/releases.`);
  process.exit(0);
}

const files = new Set(found);
const versions = new Set();
for (const channel of found) {
  const text = fs.readFileSync(path.join(dist, channel), "utf8");
  for (const match of text.matchAll(/^\s*-?\s*(?:url|path):\s*(.+?)\s*$/gm)) {
    const name = match[1].replace(/^['"]|['"]$/g, "");
    files.add(name);
    files.add(`${name}.blockmap`);
  }
  const version = /^version:\s*(\S+)/m.exec(text)?.[1];
  if (version) versions.add(version);
}

fs.mkdirSync(releases, { recursive: true });
for (const old of fs.readdirSync(releases)) {
  if (old !== "README.md") fs.rmSync(path.join(releases, old), { recursive: true, force: true });
}
let size = 0;
for (const name of files) {
  const from = path.join(dist, name);
  if (!fs.existsSync(from)) continue; // (not every file has a blockmap)
  fs.copyFileSync(from, path.join(releases, name));
  size += fs.statSync(from).size;
}
console.log(
  `Desktop release ${[...versions].join(", ")} (${found.join(", ")}) copied to backend/releases: ` +
    `${files.size} files, ${(size / 1e6).toFixed(0)} MB`,
);
