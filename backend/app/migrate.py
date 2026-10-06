"""Bring the database up to date (`python -m app.migrate`): what `alembic upgrade head` does,
but found from this package, so it works from any directory and whatever alembic.ini says."""

from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ini = ROOT / "alembic.ini"
    config = Config(str(ini)) if ini.is_file() else Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
