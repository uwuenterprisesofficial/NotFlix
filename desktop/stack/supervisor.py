"""Runs the desktop app's built-in server: every service, started in order, watched, stopped.

    python launcher.py supervise

The app writes one JSON line to stdin with what to start (see `start`), and reads JSON lines
from stdout: {"ready": {"url": ..., "key": ...}} once the API answers, or {"error": "..."}.
A {"stop": true} line, or stdin closing (the app quit or crashed), stops everything.

This runs in Python rather than in the app's own (Electron) Node.js: there, starting
PostgreSQL's server could stall the app's event loop, and Python's child processes don't
inherit the app's open files.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
HOST = "127.0.0.1"
FIRST_PORT = 47310
START_TIMEOUT_S = 120
MAX_RESTARTS = 5
# No console window for each service on Windows.
CREATE_NO_WINDOW = 0x08000000 if WINDOWS else 0


def exe(name: str) -> str:
    return f"{name}.exe" if WINDOWS else name


def free_ports(count: int, taken: list[int]) -> list[int]:
    ports: list[int] = []
    for port in range(FIRST_PORT, FIRST_PORT + 200):
        if len(ports) == count:
            break
        if port in taken:
            continue
        with socket.socket() as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
        ports.append(port)
    if len(ports) < count:
        raise RuntimeError("Not enough free ports for the built-in server")
    return ports


class Supervisor:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.log_dir = data_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.services: dict[str, subprocess.Popen] = {}
        self.failed: str | None = None
        self.stopping = False
        self.postgres: Path | None = None
        self.lock = threading.Lock()

    # --- processes ---

    def log_file(self, name: str):
        log = open(self.log_dir / f"{name}.log", "ab")  # noqa: SIM115 (the child keeps it)
        log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n".encode())
        log.flush()
        return log

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
        env.update(extra or {})
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        # ffmpeg for the intro/outro detection.
        env["PATH"] = f"{HERE / 'bin'}{os.pathsep}{env.get('PATH', '')}"
        return env

    def popen(self, name: str, args: list[str], env=None, cwd: Path = HERE) -> subprocess.Popen:
        log = self.log_file(name)
        try:
            return subprocess.Popen(
                args, cwd=cwd, env=self.env(env), stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW,
            )  # fmt: skip
        finally:
            log.close()  # the child has its own handle

    def run_once(self, name: str, args: list[str], env=None, timeout: float = 300) -> None:
        """A command that has to finish successfully before going on. (Its output goes to a
        file, not a pipe: PostgreSQL's server, started by pg_ctl, would keep a pipe open.)"""
        log = self.log_file(name)
        try:
            code = subprocess.run(
                args, cwd=HERE, env=self.env(env), stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW, timeout=timeout, check=False,
            ).returncode  # fmt: skip
        finally:
            log.close()
        if code != 0:
            raise RuntimeError(f"{name} failed (exit {code}); see {self.log_dir / name}.log")

    def service(self, name: str, args: list[str], env=None, cwd: Path = HERE) -> None:
        """A long-running service, started again (a few times) when it stops by itself."""
        with self.lock:
            self.services[name] = self.popen(name, args, env, cwd)

        def watch(restarts: int = 0) -> None:
            while True:
                process = self.services.get(name)
                if process is None:
                    return
                code = process.wait()
                if self.stopping:
                    return
                if restarts >= MAX_RESTARTS:
                    self.failed = f"{name} stopped (exit {code}); see {self.log_dir / name}.log"
                    return
                restarts += 1
                time.sleep(restarts)
                with self.lock:
                    if self.stopping:
                        return
                    self.services[name] = self.popen(name, args, env, cwd)

        threading.Thread(target=watch, daemon=True).start()

    def wait_until(self, check, name: str) -> None:
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.failed:
                raise RuntimeError(self.failed)
            if check():
                return
            time.sleep(0.2)
        raise RuntimeError(f"{name} didn't start; see {self.log_dir / name}.log")

    # --- PostgreSQL ---

    def pg(self, tool: str) -> str:
        return str(HERE / "postgres" / "bin" / exe(tool))

    def start_postgres(self, data: Path, port: int, password: str) -> None:
        if not (data / "PG_VERSION").exists():
            shutil.rmtree(data, ignore_errors=True)
            data.parent.mkdir(parents=True, exist_ok=True)
            password_file = data.parent / f"pw-{os.getpid()}"
            password_file.write_text(password)
            try:
                self.run_once("postgres-init", [
                    self.pg("initdb"), "-D", str(data), "-U", "notflix",
                    f"--pwfile={password_file}", "-A", "scram-sha-256", "-E", "UTF8", "--no-locale",
                ])  # fmt: skip
            finally:
                password_file.unlink(missing_ok=True)
        # Still running from a run that didn't end cleanly: stop it, it may have another port.
        try:
            self.run_once(
                "postgres-ctl", [self.pg("pg_ctl"), "stop", "-D", str(data), "-m", "fast", "-w"]
            )
        except RuntimeError:
            pass  # wasn't running
        options = f"-p {port} -c listen_addresses={HOST}"
        if not WINDOWS:
            options += " -c unix_socket_directories="
        self.run_once("postgres-ctl", [
            self.pg("pg_ctl"), "start", "-D", str(data), "-w", "-t", str(START_TIMEOUT_S),
            "-l", str(self.log_dir / "postgres.log"), "-o", options,
        ])  # fmt: skip
        self.postgres = data

    # --- everything ---

    def start(self, options: dict) -> dict:
        web_origin = options["webOrigin"]
        secret = options["secrets"]
        extra_env: dict[str, str] = {k: str(v) for k, v in (options.get("env") or {}).items()}
        components = set(options.get("components") or [])
        pg_port, redis_port, api_port, scraper_port, anivexa_port, aniworld_port = free_ports(
            6, options.get("taken") or []
        )
        api = f"http://{HOST}:{api_port}"
        python = sys.executable
        launcher = str(HERE / "launcher.py")

        self.start_postgres(self.data_dir / "postgres", pg_port, secret["dbPassword"])
        self.service("redis", [python, launcher, "redis", "--port", str(redis_port)])

        backend_env = {
            "DATABASE_URL": (
                f"postgresql+psycopg://notflix:{secret['dbPassword']}@{HOST}:{pg_port}/notflix"
            ),
            "REDIS_URL": f"redis://{HOST}:{redis_port}/0",
            "API_KEY": secret["apiKey"],
            "SECRET_KEY": secret["secretKey"],
            "FRONTEND_URL": web_origin,
            "MAL_REDIRECT_URI": f"{web_origin}/api/auth/callback",
            "ANILIST_REDIRECT_URI": f"{web_origin}/api/auth/anilist/callback",
            "ANISCRAPER_URL": f"http://{HOST}:{scraper_port}",
            "ANIVEXA_URL": f"http://{HOST}:{anivexa_port}" if "anivexa" in components else "",
            "ANIWORLD_API_URL": (
                f"http://{HOST}:{aniworld_port}" if "aniworld-api" in components else ""
            ),
            "MEDIA_DIR": str(self.data_dir / "media"),
            **extra_env,
        }

        def port_open(port: int):
            def check() -> bool:
                with socket.socket() as s:
                    s.settimeout(0.5)
                    return s.connect_ex((HOST, port)) == 0

            return check

        self.wait_until(port_open(redis_port), "redis")
        self.run_once("setup", [python, launcher, "setup"], backend_env)

        self.service("api", [python, launcher, "api", "--port", str(api_port)], backend_env)
        self.service("worker-analysis", [python, launcher, "worker", "analysis"], backend_env)
        self.service("worker-catalog", [python, launcher, "worker", "catalog"], backend_env)
        self.service("aniscraper", [python, launcher, "aniscraper", "--port", str(scraper_port)])
        if "anivexa" in components and options.get("node"):
            self.service(
                "anivexa",
                [options["node"], "-r", str(HERE / "loopback.cjs"), "server.js"],
                {"ELECTRON_RUN_AS_NODE": "1", "PORT": str(anivexa_port)},
                HERE / "anivexa",
            )
        if "aniworld-api" in components:
            host = extra_env.get("ANIWORLD_URL", "").rstrip("/")
            self.service(
                "aniworld-api",
                [
                    str(HERE / "aniworld-api" / exe("aniworld-api")),
                    "--urls",
                    f"http://{HOST}:{aniworld_port}",
                ],
                {"ANIWORLD_HOST": f"{host}/" if host else ""},
            )

        def api_up() -> bool:
            request = urllib.request.Request(
                f"{api}/health", headers={"x-api-key": secret["apiKey"]}
            )
            try:
                with urllib.request.urlopen(request, timeout=2) as res:
                    return res.status == 200
            except (urllib.error.URLError, OSError):
                return False

        self.wait_until(api_up, "api")
        return {"url": api, "key": secret["apiKey"]}

    def stop(self) -> None:
        self.stopping = True
        with self.lock:
            processes = list(self.services.values())
            self.services.clear()
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        if self.postgres is not None:
            try:
                self.run_once(
                    "postgres-ctl",
                    [self.pg("pg_ctl"), "stop", "-D", str(self.postgres), "-m", "fast", "-w"],
                    timeout=60,
                )
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
            self.postgres = None


def say(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def supervise() -> None:
    first = sys.stdin.readline()
    if not first:
        return
    options = json.loads(first)
    supervisor = Supervisor(Path(options["dataDir"]))
    try:
        say({"ready": supervisor.start(options)})
    except Exception as e:  # noqa: BLE001 (reported to the app)
        supervisor.stop()
        say({"error": str(e)})
        return
    # Until the app says stop, or goes away.
    for line in sys.stdin:
        if json.loads(line or "{}").get("stop"):
            break
    supervisor.stop()
