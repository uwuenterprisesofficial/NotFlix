import pytest

from app.core.api_key import check_configured


@pytest.fixture
async def anonymous(client):
    """A client without the API key."""
    client.headers.pop("x-api-key")
    return client


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/health", "/me", "/browse", "/auth/providers", "/docs"])
async def test_nothing_answers_without_the_key(anonymous, path):
    res = await anonymous.get(path)
    assert res.status_code == 401 and res.json() == {"detail": "Invalid or missing API key"}
    assert "set-cookie" not in res.headers
    wrong = await anonymous.get(path, headers={"x-api-key": "wrong-key-0123456789"})
    assert wrong.status_code == 401


@pytest.mark.anyio
async def test_with_the_key(client):
    assert (await client.get("/health")).json() == {"status": "ok"}


@pytest.mark.anyio
async def test_oauth_redirects_come_without_it(anonymous):
    # The provider sends the browser back without the key; without a sign-in started with the
    # key (its state), they only report a failed sign-in.
    for path in ("/auth/callback", "/auth/anilist/callback"):
        res = await anonymous.get(path, params={"code": "c", "state": "made-up"})
        assert res.status_code == 307 and res.headers["location"].endswith("&reason=expired")


@pytest.mark.parametrize(
    ("key", "says"), [("", "isn't set in this container"), ("short", "it has 5")]
)
def test_the_api_needs_a_key(key, says):
    with pytest.raises(RuntimeError, match=says):
        check_configured(key)
    check_configured("x" * 16)
