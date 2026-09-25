import pytest
from sqlalchemy import delete

from app.providers.aniworld import parse_description

pytestmark = pytest.mark.anyio


def test_parse_description_prefers_the_full_text():
    html = '<p class="seri_des" data-full-description="Die ganze Geschichte.">Die ganze…</p>'
    assert parse_description(html) == "Die ganze Geschichte."
    assert parse_description('<p class="seri_des"> Kurz. </p>') == "Kurz."
    assert parse_description("<p>nothing</p>") is None


class FakeAniWorld:
    name = "aniworld"

    def __init__(self, text):
        self.text = text
        self.calls = 0

    async def description(self, anime):
        self.calls += 1
        return self.text


@pytest.fixture
def show(database):
    from app.db.session import sync_session
    from app.models import Anime, AnimeSynopsis

    with sync_session() as db:
        db.execute(delete(AnimeSynopsis))
        db.merge(Anime(id=77, title="Show", synopsis="English synopsis.", genres=[]))
        db.commit()


async def test_german_synopsis_is_looked_up_once_and_stored(client, show, monkeypatch):
    from app.providers import base

    fake = FakeAniWorld("Deutsche Beschreibung.")
    monkeypatch.setattr(base, "enabled_providers", lambda: [fake])

    # Not known yet: the detail stays English.
    detail = (await client.get("/anime/77", params={"lang": "de"})).json()
    assert detail["synopsis_language"] == "en"

    for _ in range(2):
        body = (await client.get("/anime/77/synopsis", params={"lang": "de"})).json()
        assert body == {"language": "de", "synopsis": "Deutsche Beschreibung."}
    assert fake.calls == 1

    detail = (await client.get("/anime/77", params={"lang": "de"})).json()
    assert (detail["synopsis"], detail["synopsis_language"]) == ("Deutsche Beschreibung.", "de")
    # English is MAL's.
    assert (await client.get("/anime/77", params={"lang": "en"})).json()["synopsis"] == (
        "English synopsis."
    )


async def test_missing_german_synopsis_falls_back_to_english(client, show, monkeypatch):
    from app.providers import base

    fake = FakeAniWorld(None)
    monkeypatch.setattr(base, "enabled_providers", lambda: [fake])
    for _ in range(2):
        body = (await client.get("/anime/77/synopsis", params={"lang": "de"})).json()
        assert body == {"language": "en", "synopsis": "English synopsis."}
    assert fake.calls == 1  # a miss is remembered too
    body = (await client.get("/anime/77/synopsis", params={"lang": "fr"})).json()
    assert body["language"] == "en"
