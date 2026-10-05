// Builds the web frontend for the desktop app and copies its standalone server to server/,
// which the app runs (and electron-builder packs). `--no-build` copies the last build.

import { execSync } from "node:child_process";
import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const desktop = join(dirname(fileURLToPath(import.meta.url)), "..");
const frontend = join(desktop, "..", "frontend");
const target = join(desktop, "server");

function run(command) {
  execSync(command, {
    cwd: frontend,
    stdio: "inherit",
    env: { ...process.env, NOTFLIX_DESKTOP_BUILD: "1", NEXT_TELEMETRY_DISABLED: "1" },
  });
}

if (!process.argv.includes("--no-build")) {
  if (!existsSync(join(frontend, "node_modules"))) run("npm ci");
  run("npm run build");
}

const standalone = join(frontend, ".next", "standalone");
if (!existsSync(join(standalone, "server.js"))) {
  throw new Error(`No standalone build in ${standalone}: run without --no-build`);
}
rmSync(target, { recursive: true, force: true });
cpSync(standalone, target, { recursive: true });
// The standalone output leaves out the static files; the server serves them from here.
cpSync(join(frontend, ".next", "static"), join(target, ".next", "static"), { recursive: true });
if (existsSync(join(frontend, "public"))) {
  cpSync(join(frontend, "public"), join(target, "public"), { recursive: true });
}
console.log(`Server copied to ${target}`);
