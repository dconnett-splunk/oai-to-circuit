import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from oai_to_circuit.app import create_app
from oai_to_circuit.config import BackendConfig, BridgeConfig


class _FakeCircuitAsyncClient:
    """Stand-in for httpx.AsyncClient used *inside* the app to call Circuit."""

    post_call_count = 0
    send_call_count = 0
    recorded_posts: list[tuple[str, dict, dict]] = []
    recorded_sends: list[httpx.Request] = []

    def __init__(self, *args, timeout=None, **kwargs) -> None:
        self.timeout = timeout
        self.calls: list[tuple[str, dict, dict]] = []

    @classmethod
    def reset_counts(cls) -> None:
        cls.post_call_count = 0
        cls.send_call_count = 0
        cls.recorded_posts = []
        cls.recorded_sends = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aclose(self):
        return None

    def build_request(self, method: str, url: str, json=None, headers=None):
        return httpx.Request(method, url, json=json, headers=headers)

    async def post(self, url: str, json=None, headers=None):
        type(self).post_call_count += 1
        self.calls.append((url, json or {}, headers or {}))
        type(self).recorded_posts.append((url, json or {}, headers or {}))
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

    async def send(self, request: httpx.Request, stream: bool = False):
        type(self).send_call_count += 1
        type(self).recorded_sends.append(request)
        stream_body = (
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            b'data: {"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            content=stream_body,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            request=request,
        )


def _make_test_config(
    *,
    quota_db_path: str,
    require_subkey: bool,
    circuit_appkey: str = "",
    default_backend_id: str = "default",
    backend_configs: dict[str, BackendConfig] | None = None,
) -> BridgeConfig:
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
        splunk_verify_ssl=True,
        admin_username="admin",
        admin_password="",
        admin_title="Circuit Bridge Admin",
        default_backend_id=default_backend_id,
        backend_configs=backend_configs or {},
    )

def test_health_check_flags(tmp_path: Path):
    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False))
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        payload = r.json()
        assert payload["status"] == "healthy"
        assert payload["credentials_configured"] is True
        assert payload["backends_configured"] == 1
        assert payload["default_backend_id"] == "default"


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


def test_chat_completion_routes_subkey_to_assigned_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import app as app_mod

    quota_db = tmp_path / "quota.db"

    async def _tok(**kwargs) -> str:
        return f"token-{kwargs['client_id']}"

    _FakeCircuitAsyncClient.reset_counts()
    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)
    monkeypatch.setattr(
        app_mod,
        "load_quotas_from_env_or_file",
        lambda: {
            "_users": {
                "sk": {
                    "backend_id": "team-b",
                    "rules": {"gpt-4o-mini": {"requests": 10}},
                }
            }
        },
    )

    app = create_app(
        config=_make_test_config(
            quota_db_path=str(quota_db),
            require_subkey=False,
            circuit_appkey="default-ak",
            default_backend_id="default",
            backend_configs={
                "default": BackendConfig(
                    client_id="client-a",
                    client_secret="secret-a",
                    appkey="appkey-a",
                    token_url="https://example.invalid/token-a",
                    circuit_base="https://example.invalid/a",
                    api_version="2025-04-01-preview",
                ),
                "team-b": BackendConfig(
                    client_id="client-b",
                    client_secret="secret-b",
                    appkey="appkey-b",
                    token_url="https://example.invalid/token-b",
                    circuit_base="https://example.invalid/b",
                    api_version="2025-05-01-preview",
                ),
            },
        )
    )
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            headers={"X-Bridge-Subkey": "sk"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200

    assert len(_FakeCircuitAsyncClient.recorded_posts) == 1
    url, payload, headers = _FakeCircuitAsyncClient.recorded_posts[0]
    assert url == "https://example.invalid/b/openai/deployments/gpt-4o-mini/chat/completions?api-version=2025-05-01-preview"
    assert headers["api-key"] == "token-client-b"
    assert payload["user"] == '{"appkey": "appkey-b"}'


def test_chat_completion_rejects_unknown_assigned_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import app as app_mod

    monkeypatch.setattr(
        app_mod,
        "load_quotas_from_env_or_file",
        lambda: {"_users": {"sk": {"backend_id": "missing", "rules": {"gpt-4o-mini": {"requests": 10}}}}},
    )

    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False))
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"X-Bridge-Subkey": "sk"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 503
    assert "unknown backend" in response.json()["detail"].lower()


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


def test_chat_completion_streaming_only_sends_one_upstream_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from oai_to_circuit import app as app_mod

    quota_db = tmp_path / "quota.db"

    async def _tok(**kwargs) -> str:
        return "token"

    _FakeCircuitAsyncClient.reset_counts()
    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)
    monkeypatch.setattr(
        app_mod,
        "load_quotas_from_env_or_file",
        lambda: {"sk": {"gpt-5": {"requests": 10, "total_tokens": 999}}},
    )

    app = create_app(config=_make_test_config(quota_db_path=str(quota_db), require_subkey=False))
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            headers={"X-Bridge-Subkey": "sk"},
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert r.status_code == 200
        assert "data:" in r.text

    assert _FakeCircuitAsyncClient.send_call_count == 1
    assert _FakeCircuitAsyncClient.post_call_count == 0


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


def test_chat_completion_emits_free_tier_billing_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import app as app_mod

    sent_events: list[dict] = []

    async def _tok(**kwargs) -> str:
        return "token"

    def _send_usage_event(
        self,
        subkey: str,
        model: str,
        requests: int = 1,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        additional_fields=None,
        preserve_timestamp: bool = False,
        friendly_name=None,
        email=None,
    ) -> bool:
        sent_events.append(
            {
                "subkey": subkey,
                "model": model,
                "requests": requests,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "additional_fields": additional_fields or {},
                "friendly_name": friendly_name,
                "email": email,
            }
        )
        return True

    monkeypatch.setattr(app_mod, "get_access_token", _tok)
    monkeypatch.setattr(app_mod.httpx, "AsyncClient", _FakeCircuitAsyncClient)
    monkeypatch.setattr(
        app_mod,
        "load_quotas_from_env_or_file",
        lambda: {"sk": {"gpt-5-nano": {"requests": 10}}},
    )
    monkeypatch.setattr(app_mod.SplunkHEC, "send_usage_event", _send_usage_event)

    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False))
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            headers={"X-Bridge-Subkey": "sk"},
            json={"model": "gpt-5-nano", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200

    assert len(sent_events) == 1
    event = sent_events[0]
    fields = event["additional_fields"]
    assert event["model"] == "gpt-5-nano"
    assert fields["pricing_tier"] == "free"
    assert fields["pricing_tier_mode"] == "auto"
    assert fields["free_tier_eligible"] is True
    assert fields["estimated_cost_usd"] == pytest.approx(0.0)
    assert fields["estimated_payg_cost_usd"] > 0
    assert fields["free_prompt_tokens_applied"] == 2
    assert fields["free_completion_tokens_applied"] == 3
    assert fields["billable_prompt_tokens"] == 0
    assert fields["billable_completion_tokens"] == 0
    assert fields["billing_period_month"]


def test_chat_completion_options_preflight_succeeds(tmp_path: Path):
    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "q.db"), require_subkey=False))
    with TestClient(app) as client:
        r = client.options(
            "/v1/chat/completions",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,x-bridge-subkey,content-type",
            },
        )

    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "*"
    assert "POST" in r.headers["access-control-allow-methods"]
