"""Runs the parts of NotFlix's server for the desktop app's built-in server (see the README).

    python launcher.py supervise              all of them, as the app asks (supervisor.py)
    python launcher.py redis --port P         a Redis-compatible in-memory server (fakeredis)
    python launcher.py setup                  create the database if needed, run migrations
    python launcher.py api --port P           the FastAPI backend
    python launcher.py worker QUEUE [...]     an RQ worker for these queues
    python launcher.py aniscraper --port P    the AniScraper service

The backend's settings come from the environment, as in Docker. Everything listens on
127.0.0.1 only. The backend and AniScraper sources sit next to this file (backend/,
aniscraper/), as the build script puts them.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE / "backend"
ANISCRAPER = HERE / "aniscraper"
HOST = "127.0.0.1"

if sys.platform == "win32":
    # Psycopg's async mode doesn't work with the Proactor event loop (Windows' default); the
    # backend's jobs start their own loops with asyncio.run, so this is set for the process.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _serve(app: str, directory: Path, port: int) -> None:
    import uvicorn

    sys.path.insert(0, str(directory))
    os.chdir(directory)
    config = uvicorn.Config(app, host=HOST, port=port, loop="none", proxy_headers=False)
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=asyncio.SelectorEventLoop)


def redis_server(port: int) -> None:
    import redis
    from fakeredis import TcpFakeServer
    from fakeredis._clients._tcp_server import LOGGER, TCPFakeRequestHandler

    class Handler(TCPFakeRequestHandler):
        """fakeredis closes a connection after any error reply (e.g. an unknown command), which
        the client only notices on its next command. Real Redis keeps it open: so does this."""

        def handle(self) -> None:
            client = self.current_client
            while not self.server._shutdown_event.is_set():
                try:
                    if client.can_read():
                        try:
                            response = client.read_response()
                        except redis.ResponseError as e:
                            response = e
                        self.writer.dump(response)
                        continue
                    data = self.rfile.readline()
                    if data == b"":
                        import select

                        readable, _, _ = select.select([self.connection], [], [], 0.01)
                        if not readable:
                            continue
                        data = self.rfile.readline()
                        if data == b"":
                            break
                    client.get_socket().sendall(data)
                except ConnectionError:
                    break
                except Exception as e:  # noqa: BLE001
                    LOGGER.debug("!!! %s: %s", self.client_address[0], e)
                    self.writer.dump(e)
                    break

    server = TcpFakeServer((HOST, port))
    server.RequestHandlerClass = Handler
    server.daemon_threads = True
    print(f"Redis (fakeredis) on {HOST}:{port}", flush=True)
    server.serve_forever()


def setup() -> None:
    """Create the database (on first start) and bring its tables up to date."""
    import psycopg
    from sqlalchemy.engine import make_url

    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    from app.core.config import get_settings

    url = make_url(get_settings().database_url)
    with psycopg.connect(
        host=url.host, port=url.port, user=url.username, password=url.password,
        dbname="postgres", autocommit=True,
    ) as conn:  # fmt: skip
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,))
        if exists.fetchone() is None:
            conn.execute(f'CREATE DATABASE "{url.database}"')
            print(f"Created database {url.database}", flush=True)

    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    print("Database up to date", flush=True)


def worker(queues: list[str]) -> None:
    """An RQ worker that runs jobs in its own process (SimpleWorker): RQ's default worker
    forks, which Windows can't. Job time limits use a timer there instead of SIGALRM."""
    from redis import Redis
    from rq import Queue, SimpleWorker

    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    from app.core.config import get_settings

    connection = Redis.from_url(get_settings().redis_url)
    SimpleWorker([Queue(q, connection=connection) for q in queues], connection=connection).work(
        with_scheduler=False
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("redis", "api", "aniscraper"):
        sub.add_parser(name).add_argument("--port", type=int, required=True)
    sub.add_parser("setup")
    sub.add_parser("supervise")
    sub.add_parser("worker").add_argument("queues", nargs="+")
    args = parser.parse_args()

    if args.command == "redis":
        redis_server(args.port)
    elif args.command == "setup":
        setup()
    elif args.command == "supervise":
        from supervisor import supervise

        supervise()
    elif args.command == "api":
        _serve("app.main:app", BACKEND, args.port)
    elif args.command == "aniscraper":
        _serve("main:app", ANISCRAPER, args.port)
    elif args.command == "worker":
        worker(args.queues)


if __name__ == "__main__":
    main()
