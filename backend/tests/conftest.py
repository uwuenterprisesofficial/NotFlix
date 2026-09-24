import os

import pytest

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://notflix:notflix@localhost:5432/notflix_test"
)
os.environ["MAL_CLIENT_ID"] = ""
# Tests never reach external streaming sites; provider tests inject their own HTTP clients.
os.environ["ANIWORLD_URL"] = ""
os.environ["ANIVEXA_URL"] = ""


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def database():
    """Fresh schema in the test database; tests using it are skipped when Postgres is down."""
    from sqlalchemy.exc import OperationalError

    from app import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import sync_engine

    try:
        with sync_engine.connect():
            pass
    except OperationalError as e:
        pytest.skip(f"Postgres not reachable: {e.orig}")
    Base.metadata.drop_all(sync_engine)
    Base.metadata.create_all(sync_engine)
    yield
    Base.metadata.drop_all(sync_engine)


@pytest.fixture
async def client(database):
    from httpx import ASGITransport, AsyncClient

    from app.db.session import async_engine
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    # Pooled async connections are bound to this test's event loop.
    await async_engine.dispose()


@pytest.fixture
def user(database):
    from datetime import UTC, datetime

    from sqlalchemy import delete

    from app.api.deps import current_user_optional
    from app.db.session import sync_session
    from app.main import app
    from app.models import User

    with sync_session() as db:
        db.execute(delete(User))
        u = User(
            mal_user_id=1,
            name="tester",
            access_token="a",
            refresh_token="r",
            token_expires_at=datetime(2100, 1, 1, tzinfo=UTC),
        )
        db.add(u)
        db.commit()
        app.dependency_overrides[current_user_optional] = lambda: u
        return u
