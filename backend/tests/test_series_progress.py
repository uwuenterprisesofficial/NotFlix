import pytest
from sqlalchemy import delete

from app.db.session import sync_session
from app.models import SeriesProgress

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def clean(database):
    with sync_session() as db:
        db.execute(delete(SeriesProgress))
        db.commit()


async def test_progress_of_a_series_is_kept(client, user):
    assert (await client.get("/series/progress")).json() == []
    body = {"title": "Dark", "image_url": "https://s.to/x.jpg", "season": 1, "episode": 2}
    assert (await client.put("/series/dark/progress", json=body)).status_code == 200
    # The next episode replaces it (one per series).
    await client.post("/series/dark/progress", json={**body, "episode": 3})
    await client.put("/series/other/progress", json={**body, "title": "Other"})
    items = (await client.get("/series/progress")).json()
    assert [(i["slug"], i["episode"]) for i in items] == [("other", 1), ("dark", 3)]
    assert (await client.delete("/series/dark/progress")).status_code == 204
    assert [i["slug"] for i in (await client.get("/series/progress")).json()] == ["other"]


async def test_image_must_be_a_web_address(client, user):
    body = {"title": "Dark", "image_url": "javascript:alert(1)", "season": 1, "episode": 1}
    saved = (await client.put("/series/dark/progress", json=body)).json()
    assert saved["image_url"] is None
