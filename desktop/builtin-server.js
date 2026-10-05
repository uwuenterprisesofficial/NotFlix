// The built-in server: NotFlix's backend and everything it needs, run on this PC from the
// bundle that scripts/prepare-stack.mjs builds (build/stack/, resources/stack/ when packaged).
//
//   PostgreSQL          the database (its data in the app's data folder, server/postgres/)
//   Redis stand-in      fakeredis, in memory (caches and job queues)
//   backend             the FastAPI API, and two workers (analysis, catalog)
//   AniScraper          AniWorld and AnimeToast
//   Anivexa             English sources (run with the app's own Node.js)
//   aniworld-api        AniWorld through SerienStreamAPI (used when chosen in the settings)
//
// Everything listens on 127.0.0.1 only, with passwords and keys made for this installation.
// The services are started, watched and stopped by the bundle's Python (stack/supervisor.py),
// which this talks to over its stdin and stdout.

const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const STOP_TIMEOUT_MS = 60_000;

/** KEY=VALUE lines (# comments), e.g. the user's server.env. */
function readEnvFile(file) {
  const env = {};
  try {
    for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
      const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
      if (match) env[match[1]] = match[2].replace(/^(["'])(.*)\1$/, "$2");
    }
  } catch {
    // no file: nothing extra
  }
  return env;
}

class BuiltInServer {
  /** The bundle in `dir`, or null when this app was built without it. */
  static find(dir) {
    try {
      const manifest = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
      return new BuiltInServer(dir, manifest);
    } catch {
      return null;
    }
  }

  /** The passwords and keys of a new installation (kept by the app between runs). */
  static secrets() {
    const secret = () => crypto.randomBytes(24).toString("base64url");
    return { apiKey: secret(), secretKey: secret(), dbPassword: secret() };
  }

  constructor(dir, manifest) {
    this.dir = dir;
    this.manifest = manifest;
    this.child = null;
  }

  has(component) {
    return this.manifest.components.includes(component);
  }

  /**
   * Start everything: `dataDir` keeps the database and logs, `webOrigin` is where the app's
   * pages are served (sign-ins return there), `secrets` from `secrets()`, `env` adds to the
   * backend's settings, `node` runs Anivexa, `taken` are ports not to use. Resolves with the
   * API's address and key once it answers.
   */
  start({ dataDir, webOrigin, secrets, env = {}, node, taken = [] }) {
    fs.mkdirSync(path.join(dataDir, "logs"), { recursive: true });
    const child = spawn(
      path.join(this.dir, this.manifest.python),
      [path.join(this.dir, "launcher.py"), "supervise"],
      {
        cwd: this.dir,
        stdio: ["pipe", "pipe", fs.openSync(path.join(dataDir, "logs", "supervisor.log"), "a")],
        windowsHide: true,
      },
    );
    this.child = child;
    const components = this.manifest.components;
    child.stdin.write(
      `${JSON.stringify({ dataDir, webOrigin, secrets, env, node, taken, components })}\n`,
    );
    return new Promise((resolve, reject) => {
      readline.createInterface({ input: child.stdout }).on("line", (line) => {
        let message;
        try {
          message = JSON.parse(line);
        } catch {
          return;
        }
        if (message.ready) resolve(message.ready);
        else if (message.error) reject(new Error(message.error));
      });
      child.on("error", reject);
      child.on("exit", (code) =>
        reject(new Error(`The built-in server stopped (exit ${code}); see its logs`)),
      );
    });
  }

  /** Stop everything (the supervisor stops on "stop", or when its stdin closes). */
  stop() {
    const child = this.child;
    this.child = null;
    if (!child || child.exitCode !== null) return Promise.resolve();
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        child.kill();
        resolve();
      }, STOP_TIMEOUT_MS);
      child.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
      child.stdin.end(`${JSON.stringify({ stop: true })}\n`);
    });
  }
}

module.exports = { BuiltInServer, readEnvFile };
