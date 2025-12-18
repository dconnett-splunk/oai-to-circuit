import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from oai_to_circuit.app import create_app
from oai_to_circuit.config import BridgeConfig


class _FakeCircuitAsyncClient:
    """Stand-in for httpx.AsyncClient used *inside* the app to call Circuit."""

    def __init__(self, *args, timeout=None, **kwargs) -> None:
        self.timeout = timeout
        self.calls: list[tuple[str, dict, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json=None, headers=None):
        self.calls.append((url, json or {}, headers or {}))
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "id": "cmpl_test",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
            headers={"content-type": "application/json"},
            request=req,
        )


def _make_test_config(*, quota_db_path: str, require_subkey: bool, circuit_appkey: str = "") -> BridgeConfig:
    # Dummy values only; these are not real credentials.
    return BridgeConfig(
        circuit_client_id="x",
        circuit_client_secret="y",
        circuit_appkey=circuit_appkey,
        token_url="https://example.invalid/token",
        circuit_base="https://example.invalid",
        api_version="2025-04-01-preview",
        quota_db_path=quota_db_path,
        require_subkey=require_subkey,
        splunk_hec_url="",
        splunk_hec_token="",
        splunk_source="oai-to-circuit",
        splunk_sourcetype="llm:usage",
        splunk_index="main",
    )

def test_health_check_flags(tmp_path: Path):
    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False))
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        payload = r.json()
        assert payload["status"] == "healthy"
        assert payload["credentials_configured"] is True


def test_chat_completion_missing_model_returns_400(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import app as app_mod

    async def _tok(**kwargs) -> str:
        return "token"

    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)

    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False))
    with TestClient(app) as client:
        r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 400
        assert r.json()["detail"] == "Model parameter required"


def test_chat_completion_invalid_json_returns_400(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import app as app_mod

    async def _tok(**kwargs) -> str:
        return "token"

    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)

    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False))
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            content=b'{"model": "gpt-4o-mini", "messages": [}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "Invalid JSON in request body"


def test_chat_completion_injects_appkey_into_user_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import app as app_mod

    async def _tok(**kwargs) -> str:
        return "token"

    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)

    app = create_app(
        config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False, circuit_appkey="ak")
    )
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200


def test_chat_completion_requires_subkey_when_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import app as app_mod

    async def _tok(**kwargs) -> str:
        return "token"

    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)

    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=True))
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 401
        assert "Subkey required" in r.json()["detail"]


def test_chat_completion_records_quota_usage_from_circuit_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from oai_to_circuit import app as app_mod

    quota_db = tmp_path / "quota.db"
    async def _tok(**kwargs) -> str:
        return "token"

    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)
    monkeypatch.setattr(
        app_mod,
        "load_quotas_from_env_or_file",
        lambda: {"sk": {"gpt-4o-mini": {"requests": 10, "total_tokens": 999}}},
    )

    app = create_app(config=_make_test_config(quota_db_path=str(quota_db), require_subkey=False))
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            headers={"X-Bridge-Subkey": "sk"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200

    conn = sqlite3.connect(str(quota_db))
    try:
        row = conn.execute(
            "SELECT requests, prompt_tokens, completion_tokens, total_tokens FROM usage WHERE subkey=? AND model=?",
            ("sk", "gpt-4o-mini"),
        ).fetchone()
        assert row == (1, 2, 3, 5)
    finally:
        conn.close()


def test_chat_completion_user_field_invalid_json_does_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import app as app_mod

    async def _tok(**kwargs) -> str:
        return "token"

    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)

    app = create_app(
        config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False, circuit_appkey="ak")
    )
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "user": "{not-json",
            },
        )
        assert r.status_code == 200
