import pytest
from sqlalchemy import delete

from app.db.session import sync_session
from app.models import SourceScan

pytestmark = pytest.mark.anyio


async def test_admin_status(client, user, monkeypatch):
    from datetime import UTC, datetime

    from app.core.config import get_settings
    from app.providers import base as providers_base

    with sync_session() as db:
        db.execute(delete(SourceScan))
        now = datetime.now(UTC)
        db.add(SourceScan(anime_id=5, provider="animetoast", status="failed", episodes=[],
                          error="AniScraper 502", started_at=now, finished_at=now))  # fmt: skip
        db.commit()
    monkeypatch.setitem(providers_base._down_until, "animetoast", 10**12)

    body = (await client.get("/admin/status")).json()
    assert {q["name"] for q in body["rq"]["queues"]} == {"analysis", "catalog"}
    [failed] = body["failed_scans"]
    assert (failed["provider"], failed["error"]) == ("animetoast", "AniScraper 502")
    toast = next(p for p in body["providers"] if p["name"] == "animetoast")
    assert toast["scans_24h"] == {"failed": 1} and toast["backoff_s"] > 0
    assert toast["last_error"]["error"] == "AniScraper 502"
    assert body["counts"]["users"] >= 1
    assert (await client.get("/me")).json()["admin"] is True

    # Retrying a provider clears its backoff and failed scans.
    assert (await client.post("/admin/providers/animetoast/retry")).status_code == 204
    assert "animetoast" not in providers_base._down_until
    assert (await client.get("/admin/status")).json()["failed_scans"] == []

    # With ADMINS set, only those users.
    monkeypatch.setattr(get_settings(), "admins", "someone-else")
    assert (await client.get("/admin/status")).status_code == 403
    assert (await client.get("/me")).json()["admin"] is False
    monkeypatch.setattr(get_settings(), "admins", "tester")
    assert (await client.get("/admin/status")).status_code == 200
