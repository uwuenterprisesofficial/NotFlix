"""Bring the database up to date (`python -m app.migrate`): what `alembic upgrade head` does,
but found from this package, so it works from any directory and whatever alembic.ini says."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parent.parent

WRONG_PASSWORD = """
NotFlix: the database doesn't accept the password in DATABASE_URL (POSTGRES_PASSWORD in
deploy/docker-compose.yml). PostgreSQL only takes POSTGRES_PASSWORD when it creates its data,
so the database volume was most likely created earlier with another password (the development
docker-compose.yml uses "notflix"). Either
  - keep the data and give the database the new password:
      docker compose exec db psql -U notflix -c "ALTER USER notflix PASSWORD '<new one>'"
  - or, if there's nothing to keep, start the database afresh (deletes it):
      docker compose down -v && docker compose up -d
"""


def main() -> None:
    ini = ROOT / "alembic.ini"
    config = Config(str(ini)) if ini.is_file() else Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    try:
        command.upgrade(config, "head")
    except OperationalError as e:
        if "password authentication failed" in str(e):
            print(WRONG_PASSWORD, file=sys.stderr)
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
