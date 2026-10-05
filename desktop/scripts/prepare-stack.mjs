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
  // npm is a .cmd script on Windows, which only runs through a shell (that splits at spaces,
  // so those arguments are quoted). Everything else is started directly.
  const shell = windows && command === "npm";
  return execFileSync(command, shell ? args.map((a) => (/\s/.test(a) ? `"${a}"` : a)) : args, {
    stdio: options.capture ? ["ignore", "pipe", "inherit"] : "inherit",
    encoding: "utf8",
    shell,
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
    // Only into the build folder: no python.exe in ~/.local/bin, no Windows registry entry.
    run("uv", [
      "python", "install", PYTHON_VERSION, "--install-dir", downloads, "--no-bin",
      ...(windows ? ["--no-registry"] : []),
    ]);
    const installed = readdirSync(downloads).find(
      (name) => name.startsWith(`cpython-${PYTHON_VERSION}`) && !name.endsWith(".lock"),
    );
    if (!installed) throw new Error(`uv didn't install Python ${PYTHON_VERSION}`);
    copy(join(downloads, installed), target);
  }
  const python = windows
    ? join(target, process.env.NOTFLIX_STACK_PYTHON ? "Scripts" : "", "python.exe")
    : join(target, "bin", "python3");

  const pip = (...args) =>
    run("uv", ["pip", "install", "--python", python, "--break-system-packages", "--no-cache", ...args]);

  // The backend's exact versions, from its lock file. Should that not install (a lock edited
  // locally, say), the newest ones its pyproject.toml allows.
  const requirements = join(work, "requirements.txt");
  const backendDeps = run(
    "uv",
    ["export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project", "--project", join(repo, "backend")],
    { capture: true },
  );
  writeFileSync(requirements, backendDeps);
  try {
    pip("-r", requirements);
  } catch {
    console.warn("The backend's lock file didn't install; using its pyproject.toml instead.");
    pip("-r", join(repo, "backend", "pyproject.toml"));
  }
  // Then AniScraper's and the launcher's: what's installed already and fits stays as it is.
  pip("-r", join(repo, "aniscraper", "requirements.txt"), ...PYTHON_EXTRAS);
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

/** Import the backend, its workers and AniScraper once with the bundled Python, so a package
 * missing from their requirements stops the build here rather than the service in the app. */
function checkImports(python) {
  const check = (name, dir, modules) => {
    const code = [
      "import importlib, sys",
      `sys.path.insert(0, ${JSON.stringify(dir)})`,
      ...modules.map((m) => `importlib.import_module(${JSON.stringify(m)})`),
    ].join("; ");
    try {
      execFileSync(python, ["-c", code], {
        cwd: dir,
        env: { ...process.env, API_KEY: "build-check-0123456789" },
        stdio: ["ignore", "ignore", "pipe"],
        encoding: "utf8",
      });
    } catch (error) {
      const missing = /No module named '([^']+)'/.exec(error.stderr ?? "")?.[1];
      const requirements = name === "AniScraper" ? "aniscraper/requirements.txt" : "backend/pyproject.toml";
      throw new Error(
        missing
          ? `${name} needs the Python package "${missing.split(".")[0]}": add it to ${requirements}`
          : `${name} doesn't start:\n${error.stderr}`,
      );
    }
  };
  check("AniScraper", join(stack, "aniscraper"), ["main"]);
  check("The backend", join(stack, "backend"), ["app.main", "app.worker.tasks", "app.worker.catalog"]);
  console.log("Backend and AniScraper import fine");
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

const DOTNET_CHANNEL = "8.0";

/** Whether `dotnet` here can build: an SDK of version 8 or newer, not just a runtime. */
function hasSdk(dotnet) {
  try {
    const sdks = run(dotnet, ["--list-sdks"], { capture: true });
    return sdks.split("\n").some((line) => Number.parseInt(line, 10) >= 8);
  } catch {
    return false;
  }
}

/** A .NET SDK: the installed one, else one put into the build folder with Microsoft's
 * dotnet-install script (no admin rights needed, nothing installed for the system). */
async function dotnetSdk() {
  if (hasSdk("dotnet")) return "dotnet";
  const dir = join(work, "dotnet");
  const local = join(dir, windows ? "dotnet.exe" : "dotnet");
  if (existsSync(local) && hasSdk(local)) return local;
  console.log(`No .NET ${DOTNET_CHANNEL} SDK found: installing one into ${dir}`);
  const script = join(work, windows ? "dotnet-install.ps1" : "dotnet-install.sh");
  const res = await fetch(`https://dot.net/v1/${windows ? "dotnet-install.ps1" : "dotnet-install.sh"}`);
  if (!res.ok) throw new Error(`Couldn't download the .NET install script (${res.status})`);
  writeFileSync(script, Buffer.from(await res.arrayBuffer()));
  if (windows) {
    run("powershell", [
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
      "-Channel", DOTNET_CHANNEL, "-InstallDir", dir, "-NoPath",
    ]);
  } else {
    run("bash", [script, "--channel", DOTNET_CHANNEL, "--install-dir", dir, "--no-path"]);
  }
  if (!hasSdk(local)) throw new Error("The .NET SDK didn't install");
  return local;
}

async function prepareAniworldApi() {
  const rid = {
    "win32-x64": "win-x64", "win32-arm64": "win-arm64", "darwin-x64": "osx-x64",
    "darwin-arm64": "osx-arm64", "linux-x64": "linux-x64", "linux-arm64": "linux-arm64",
  }[`${process.platform}-${process.arch}`];
  const dotnet = await dotnetSdk();
  run(
    dotnet,
    [
      "publish", join(desktop, "stack", "aniworld-api"), "-c", "Release", "-r", rid,
      "-o", join(stack, "aniworld-api"),
    ],
    {
      env: {
        ...process.env,
        DOTNET_CLI_TELEMETRY_OPTOUT: "1",
        DOTNET_NOLOGO: "1",
        // The SDK in the build folder finds its own runtime there.
        ...(dotnet === "dotnet" ? {} : { DOTNET_ROOT: dirname(dotnet) }),
      },
    },
  );
}

rmSync(stack, { recursive: true, force: true });
mkdirSync(work, { recursive: true });
const python = preparePython();
prepareSources();
checkImports(python);
prepareFfmpeg(python);
preparePostgres();
const components = ["postgres", "redis", "backend", "aniscraper", "ffmpeg"];
// Optional parts: without them the built-in server still works (no English sources from
// Anivexa; AniWorld only through AniScraper).
const skipped = [];
for (const [name, prepare] of [["anivexa", prepareAnivexa], ["aniworld-api", prepareAniworldApi]]) {
  if (without.has(name)) continue;
  try {
    await prepare();
    components.push(name);
  } catch (error) {
    rmSync(join(stack, name), { recursive: true, force: true });
    skipped.push(`${name}: ${error.message.split("\n")[0]}`);
  }
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
for (const reason of skipped) console.warn(`Left out ${reason}`);
