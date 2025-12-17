import pytest

import httpx
from fastapi import HTTPException

from oai_to_circuit.oauth import TokenCache, get_access_token


class _Logger:
    def __init__(self) -> None:
        self.debugs: list[str] = []
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.exceptions: list[str] = []

    def debug(self, msg: str) -> None:
        self.debugs.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def exception(self, msg: str) -> None:
        self.exceptions.append(msg)


class _FakeHTTPXClient:
    def __init__(self, *args, **kwargs) -> None:
        self.posts: list[tuple[str, dict, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, headers=None, data=None):
        self.posts.append((url, headers or {}, data or ""))
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"access_token": "tok", "expires_in": 3600},
            headers={"content-type": "application/json"},
            request=req,
        )


@pytest.mark.anyio
async def test_get_access_token_missing_creds_raises_http_500():
    logger = _Logger()
    cache = TokenCache()
    with pytest.raises(HTTPException) as exc:
        await get_access_token(
            token_url="https://example.invalid/token",
            client_id="",
            client_secret="",
            logger=logger,
            cache=cache,
        )
    assert exc.value.status_code == 500
    assert "missing CIRCUIT_CLIENT_ID" in exc.value.detail
    assert "CIRCUIT_CLIENT_SECRET" in exc.value.detail


@pytest.mark.anyio
async def test_get_access_token_caches_until_expiry(monkeypatch):
    import oai_to_circuit.oauth as oauth_mod

    logger = _Logger()
    cache = TokenCache()

    # Control time so cache logic is deterministic.
    t = {"now": 1000.0}
    monkeypatch.setattr(oauth_mod.time, "time", lambda: t["now"])

    fake_client = _FakeHTTPXClient()

    class _Factory:
        def __call__(self, *args, **kwargs):
            return fake_client

    monkeypatch.setattr(oauth_mod.httpx, "AsyncClient", _Factory())

    tok1 = await get_access_token(
        token_url="https://example.invalid/token",
        client_id="x",
        client_secret="y",
        logger=logger,
        cache=cache,
    )
    assert tok1 == "tok"
    assert len(fake_client.posts) == 1

    # Still valid (now < expires_at - 60) => cached.
    t["now"] = 1200.0
    tok2 = await get_access_token(
        token_url="https://example.invalid/token",
        client_id="x",
        client_secret="y",
        logger=logger,
        cache=cache,
    )
    assert tok2 == "tok"
    assert len(fake_client.posts) == 1


