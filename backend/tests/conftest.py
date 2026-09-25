import os

import pytest

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://notflix:notflix@localhost:5432/notflix_test"
)
os.environ["MAL_CLIENT_ID"] = ""
os.environ["ANILIST_CLIENT_ID"] = ""
# Tests never reach external streaming sites; provider tests inject their own HTTP clients.
os.environ["ANIWORLD_URL"] = ""
os.environ["ANIVEXA_URL"] = ""
os.environ["JIKAN_URL"] = ""
os.environ["ANISKIP_URL"] = ""


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

    from app.core import cache
    from app.db.session import async_engine
    from app.main import app
    from app.services import airing, list_writer, source_scan, stats_jobs

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await source_scan.wait_idle()
    await stats_jobs.wait_idle()
    await list_writer.wait_idle()
    await airing.wait_idle()
    app.dependency_overrides.clear()
    # Pooled async connections (Postgres and Redis) are bound to this test's event loop.
    await async_engine.dispose()
    await cache.close()


@pytest.fixture(autouse=True)
def clean_source_cache(request):
    """Each test that touches the database starts without cached sources or scans."""
    if "database" not in request.fixturenames:
        return
    from sqlalchemy import delete

    from app.db.session import sync_session
    from app.models import EpisodeSource, ResolvedSource, SourceScan

    request.getfixturevalue("database")
    with sync_session() as db:
        db.execute(delete(ResolvedSource))
        db.execute(delete(EpisodeSource))
        db.execute(delete(SourceScan))
        db.commit()


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
            mal_name="tester",
            access_token="a",
            refresh_token="r",
            token_expires_at=datetime(2100, 1, 1, tzinfo=UTC),
        )
        db.add(u)
        db.commit()
        app.dependency_overrides[current_user_optional] = lambda: u
        return u


@pytest.fixture(autouse=True)
def catalogue_jobs(monkeypatch):
    """Catalogue jobs are recorded instead of queued, and nothing counts as queued already."""
    from app.services import catalog_jobs

    jobs: list[tuple[list[int], list[dict], bool]] = []
    monkeypatch.setattr(
        catalog_jobs, "_enqueue_job", lambda ids, rows, refresh: jobs.append((ids, rows, refresh))
    )
    try:
        from redis import Redis

        from app.core.config import get_settings

        r = Redis.from_url(get_settings().redis_url)
        keys = list(r.scan_iter("catalog:queued:*")) + list(r.scan_iter("mal:search:*"))
        if keys:
            r.delete(*keys)
    except Exception:
        pass
    return jobs
