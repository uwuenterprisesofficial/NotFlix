// Builds the built-in server (build/stack/), which the desktop app runs on the PC instead of
// connecting to a server: PostgreSQL, a Python runtime with the backend, its workers,
// AniScraper and a Redis stand-in, Anivexa, SerienStreamAPI's AniWorld service and ffmpeg.
// Nothing needs Docker or anything installed on the PC that runs the app.
//
// Run it on the system the app is for (it fetches that system's binaries). It needs uv, git and
// npm, and the .NET 8 SDK for the SerienStreamAPI service.
//
//   node scripts/prepare-stack.mjs [--without=anivexa,aniworld-api]
//
// NOTFLIX_STACK_PYTHON=<python executable> uses a virtual environment made from that Python
// instead of a portable one (for development: the result only works on this machine).

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const desktop = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(desktop, "..");
const build = join(desktop, "build");
const work = join(build, "work");
const stack = join(build, "stack");
const windows = process.platform === "win32";

const PYTHON_VERSION = "3.12";
// Tested versions; newer ones may change what NotFlix relies on.
const ANIVEXA = { repo: "https://github.com/walterwhite-69/Anivexa-API", commit: "db8cda9c144be60f4ad9d271dcf364ac8660f018" };
const POSTGRES_PACKAGE_VERSION = "18.4.0-beta.17";
const PYTHON_EXTRAS = ["fakeredis[lua]==2.39.0"];

const without = new Set(
  (process.argv.find((a) => a.startsWith("--without="))?.slice("--without=".length) ?? "")
    .split(",")
    .filter(Boolean),
);

function run(command, args, options = {}) {
  console.log(`> ${command} ${args.join(" ")}`);
  return execFileSync(command, args, {
    stdio: options.capture ? ["ignore", "pipe", "inherit"] : "inherit",
    encoding: "utf8",
    shell: windows, // npm, uv and dotnet are .cmd/.exe shims there
    ...options,
  });
}

function copy(from, to, filter) {
  // verbatimSymlinks: PostgreSQL's libraries link to each other relatively.
  cpSync(from, to, { recursive: true, verbatimSymlinks: true, filter });
}

const skipCaches = (path) => !/[\\/](__pycache__|\.pytest_cache|\.ruff_cache|tests|\.venv)$/.test(path);

function platformName() {
  const os = { win32: "windows", darwin: "darwin", linux: "linux" }[process.platform];
  if (!os) throw new Error(`Unsupported platform ${process.platform}`);
  return `${os}-${process.arch}`;
}

// --- Python with the backend's and AniScraper's dependencies ---

function preparePython() {
  const target = join(stack, "python");
  if (process.env.NOTFLIX_STACK_PYTHON) {
    run("uv", ["venv", "--python", process.env.NOTFLIX_STACK_PYTHON, target]);
  } else {
    const downloads = join(work, "python");
    run("uv", ["python", "install", PYTHON_VERSION, "--install-dir", downloads]);
    const installed = readdirSync(downloads).find(
      (name) => name.startsWith(`cpython-${PYTHON_VERSION}`) && !name.endsWith(".lock"),
    );
    if (!installed) throw new Error(`uv didn't install Python ${PYTHON_VERSION}`);
    copy(join(downloads, installed), target);
  }
  const python = windows
    ? join(target, process.env.NOTFLIX_STACK_PYTHON ? "Scripts" : "", "python.exe")
    : join(target, "bin", "python3");

  const requirements = join(work, "requirements.txt");
  const backendDeps = run(
    "uv",
    ["export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project", "--project", join(repo, "backend")],
    { capture: true },
  );
  writeFileSync(requirements, backendDeps);
  run("uv", [
    "pip", "install", "--python", python, "--break-system-packages", "--no-cache",
    "-r", requirements, "-r", join(repo, "aniscraper", "requirements.txt"), ...PYTHON_EXTRAS,
  ]);
  return python;
}

// --- The backend, AniScraper and the launcher ---

function prepareSources() {
  const backend = join(stack, "backend");
  copy(join(repo, "backend", "app"), join(backend, "app"), skipCaches);
  copy(join(repo, "backend", "alembic"), join(backend, "alembic"), skipCaches);
  copy(join(repo, "backend", "alembic.ini"), join(backend, "alembic.ini"));
  mkdirSync(join(stack, "aniscraper"), { recursive: true });
  for (const file of readdirSync(join(repo, "aniscraper")).filter((f) => f.endsWith(".py"))) {
    copy(join(repo, "aniscraper", file), join(stack, "aniscraper", file));
  }
  copy(join(desktop, "stack", "launcher.py"), join(stack, "launcher.py"));
  copy(join(desktop, "stack", "supervisor.py"), join(stack, "supervisor.py"));
  copy(join(desktop, "stack", "loopback.cjs"), join(stack, "loopback.cjs"));
}

// --- ffmpeg (intro/outro detection), from the imageio-ffmpeg wheel for this system ---

function prepareFfmpeg(python) {
  const target = join(work, "ffmpeg");
  run("uv", ["pip", "install", "--python", python, "--target", target, "--no-cache", "imageio-ffmpeg"]);
  const binaries = join(target, "imageio_ffmpeg", "binaries");
  const binary = readdirSync(binaries).find((f) => f.startsWith("ffmpeg"));
  if (!binary) throw new Error("imageio-ffmpeg has no ffmpeg for this system");
  mkdirSync(join(stack, "bin"), { recursive: true });
  copy(join(binaries, binary), join(stack, "bin", windows ? "ffmpeg.exe" : "ffmpeg"));
}

// --- PostgreSQL, from the embedded-postgres packages ---

function preparePostgres() {
  const target = join(work, "postgres");
  mkdirSync(target, { recursive: true });
  const pkg = `@embedded-postgres/${platformName()}`;
  run("npm", ["install", "--prefix", target, "--no-save", "--no-audit", "--no-fund", `${pkg}@${POSTGRES_PACKAGE_VERSION}`]);
  copy(join(target, "node_modules", ...pkg.split("/"), "native"), join(stack, "postgres"));
}

// --- Anivexa (English sources), run with the app's own Node.js ---

function prepareAnivexa() {
  const source = join(work, "anivexa");
  rmSync(source, { recursive: true, force: true });
  run("git", ["clone", "--quiet", ANIVEXA.repo, source]);
  run("git", ["-C", source, "checkout", "--quiet", ANIVEXA.commit]);
  run("npm", ["ci", "--omit=dev", "--no-audit", "--no-fund"], { cwd: source });
  copy(source, join(stack, "anivexa"), (path) => !/[\\/]\.git$/.test(path));
}

// --- SerienStreamAPI's AniWorld service, one self-contained executable ---

function prepareAniworldApi() {
  const rid = {
    "win32-x64": "win-x64", "win32-arm64": "win-arm64", "darwin-x64": "osx-x64",
    "darwin-arm64": "osx-arm64", "linux-x64": "linux-x64", "linux-arm64": "linux-arm64",
  }[`${process.platform}-${process.arch}`];
  run("dotnet", [
    "publish", join(desktop, "stack", "aniworld-api"), "-c", "Release", "-r", rid,
    "-o", join(stack, "aniworld-api"),
  ]);
}

rmSync(stack, { recursive: true, force: true });
mkdirSync(work, { recursive: true });
const python = preparePython();
prepareSources();
prepareFfmpeg(python);
preparePostgres();
const components = ["postgres", "redis", "backend", "aniscraper", "ffmpeg"];
for (const [name, prepare] of [["anivexa", prepareAnivexa], ["aniworld-api", prepareAniworldApi]]) {
  if (without.has(name)) continue;
  prepare();
  components.push(name);
}
writeFileSync(
  join(stack, "manifest.json"),
  JSON.stringify(
    {
      platform: `${process.platform}-${process.arch}`,
      python: python.slice(stack.length + 1),
      components,
      built: new Date().toISOString(),
    },
    null,
    2,
  ),
);
console.log(`Built-in server ready in ${stack} (${components.join(", ")})`);
