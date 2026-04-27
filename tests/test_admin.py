import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from oai_to_circuit.app import create_app
from oai_to_circuit.config import BackendConfig, BridgeConfig


def _make_test_config(
    *,
    quota_db_path: str,
    admin_password: str = "",
    admin_username: str = "admin",
    default_backend_id: str = "default",
    backend_configs: dict[str, BackendConfig] | None = None,
) -> BridgeConfig:
    return BridgeConfig(
        circuit_client_id="x",
        circuit_client_secret="y",
        circuit_appkey="",
        token_url="https://example.invalid/token",
        circuit_base="https://example.invalid",
        api_version="2025-04-01-preview",
        quota_db_path=quota_db_path,
        require_subkey=False,
        splunk_hec_url="",
        splunk_hec_token="",
        splunk_source="oai-to-circuit",
        splunk_sourcetype="llm:usage",
        splunk_index="main",
        splunk_verify_ssl=True,
        admin_username=admin_username,
        admin_password=admin_password,
        admin_title="Circuit Bridge Admin",
        default_backend_id=default_backend_id,
        backend_configs=backend_configs or {},
    )


def test_admin_pages_render_usage_views(tmp_path: Path, monkeypatch):
    from oai_to_circuit import app as app_mod

    quota_db = tmp_path / "quota.db"
    monkeypatch.setattr(
        app_mod,
        "load_quotas_from_env_or_file",
        lambda: {
            "sk-alpha": {"*": {"requests": 1000, "total_tokens": 5000}},
            "sk-beta": {"gpt-4o": {"requests": 10}},
        },
    )

    app = create_app(config=_make_test_config(quota_db_path=str(quota_db)))
    with TestClient(app) as client:
        quota_manager = app.state.quota_manager
        quota_manager.upsert_subkey_profile("sk-alpha", "Alpha Team", "alpha@example.com", "Primary admin user")
        quota_manager.record_usage(
            "sk-alpha",
            "gpt-4o-mini",
            request_inc=3,
            prompt_tokens=40,
            completion_tokens=80,
            total_tokens=120,
            usage_month="2026-04",
        )
        quota_manager.record_usage(
            "sk-beta",
            "gpt-4o",
            request_inc=1,
            prompt_tokens=20,
            completion_tokens=30,
            total_tokens=50,
            usage_month="2026-04",
        )

        overview = client.get("/admin")
        assert overview.status_code == 200
        assert "Total requests" in overview.text
        assert "Alpha Team" in overview.text

        users = client.get("/admin/users")
        assert users.status_code == 200
        assert "Managed access keys" in users.text
        assert "alpha@example.com" in users.text
        assert 'datalist id="supported-models"' in users.text
        assert 'value="gpt-4o-mini"' in users.text

        detail = client.get("/admin/users/sk-alpha")
        assert detail.status_code == 200
        assert "Observed activity and current limits" in detail.text
        assert "gpt-4o-mini" in detail.text
        assert "Primary admin user" in detail.text


def test_admin_clarifies_bootstrap_default_backend_labels(tmp_path: Path):
    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "quota.db")))
    app.state.config = replace(app.state.config, legacy_default_backend_active=True)

    with TestClient(app) as client:
        backends_page = client.get("/admin/backends")
        assert backends_page.status_code == 200
        assert "credentials.env" in backends_page.text
        assert "Bootstrap from credentials.env" in backends_page.text

        users_page = client.get("/admin/users")
        assert users_page.status_code == 200
        assert "Inherit service default (default) from credentials.env" in users_page.text
        assert "default (explicit assignment, credentials.env backend)" in users_page.text


def test_admin_create_user_writes_quota_file_and_profile(tmp_path: Path, monkeypatch):
    quota_db = tmp_path / "quota.db"
    quota_file = tmp_path / "quotas.json"
    quota_file.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("QUOTAS_JSON", raising=False)
    monkeypatch.setenv("QUOTAS_JSON_PATH", str(quota_file))

    app = create_app(config=_make_test_config(quota_db_path=str(quota_db)))
    with TestClient(app) as client:
        response = client.post(
            "/admin/users",
            content=urlencode(
                [
                    ("friendly_name", "Gamma Team"),
                    ("email", "gamma@example.com"),
                    ("description", "Shared quota owner"),
                    ("prefix", "gamma"),
                    ("custom_subkey", ""),
                    ("quota_model", "*"),
                    ("quota_requests", "100"),
                    ("quota_tokens", "5000"),
                    ("quota_pricing_tier", "free"),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/admin/users/")
    subkey = location.split("/admin/users/", 1)[1].split("?", 1)[0]

    stored_quotas = json.loads(quota_file.read_text(encoding="utf-8"))
    assert stored_quotas[subkey]["*"]["requests"] == 100
    assert stored_quotas[subkey]["*"]["total_tokens"] == 5000
    assert stored_quotas[subkey]["*"]["pricing_tier"] == "free"

    conn = sqlite3.connect(str(quota_db))
    try:
        row = conn.execute(
            "SELECT friendly_name, email, description FROM subkey_names WHERE subkey=?",
            (subkey,),
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Gamma Team", "gamma@example.com", "Shared quota owner")


def test_admin_auth_can_be_enabled(tmp_path: Path):
    app = create_app(config=_make_test_config(quota_db_path=str(tmp_path / "quota.db"), admin_password="secret", admin_username="ops"))

    with TestClient(app) as client:
        unauthorized = client.get("/admin", follow_redirects=False)
        assert unauthorized.status_code == 401

        authorized = client.get("/admin", auth=("ops", "secret"))
        assert authorized.status_code == 200
        assert "Circuit Bridge Admin" in authorized.text


def test_admin_can_remove_user_quota_rules(tmp_path: Path, monkeypatch):
    from oai_to_circuit import app as app_mod

    quota_db = tmp_path / "quota.db"
    quota_file = tmp_path / "quotas.json"
    quota_file.write_text(json.dumps({"sk-remove": {"*": {"requests": 10}}}), encoding="utf-8")
    monkeypatch.delenv("QUOTAS_JSON", raising=False)
    monkeypatch.setenv("QUOTAS_JSON_PATH", str(quota_file))
    monkeypatch.setattr(app_mod, "load_quotas_from_env_or_file", lambda: json.loads(quota_file.read_text(encoding="utf-8")))

    app = create_app(config=_make_test_config(quota_db_path=str(quota_db)))
    with TestClient(app) as client:
        app.state.quota_manager.upsert_subkey_profile("sk-remove", "Remove Me", "", "")
        response = client.post(
            "/admin/users/sk-remove/quotas",
            content=urlencode(
                [
                    ("quota_model", ""),
                    ("quota_requests", ""),
                    ("quota_tokens", ""),
                    ("quota_pricing_tier", "auto"),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    stored_quotas = json.loads(quota_file.read_text(encoding="utf-8"))
    assert "sk-remove" not in stored_quotas


def test_admin_can_manage_global_rules_templates_and_user_template_assignment(tmp_path: Path, monkeypatch):
    quota_db = tmp_path / "quota.db"
    quota_file = tmp_path / "quotas.json"
    quota_file.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("QUOTAS_JSON", raising=False)
    monkeypatch.setenv("QUOTAS_JSON_PATH", str(quota_file))

    app = create_app(
        config=_make_test_config(
            quota_db_path=str(quota_db),
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
                "secondary": BackendConfig(
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
        global_response = client.post(
            "/admin/policies/global",
            content=urlencode(
                [
                    ("global_quota_model", "*"),
                    ("global_quota_requests", "250"),
                    ("global_quota_tokens", ""),
                    ("global_quota_pricing_tier", "auto"),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert global_response.status_code == 303

        template_response = client.post(
            "/admin/policies/templates",
            content=urlencode(
                [
                    ("template_name", "team-standard"),
                    ("template_description", "Shared team defaults"),
                    ("template_quota_model", "*"),
                    ("template_quota_requests", "100"),
                    ("template_quota_tokens", "5000"),
                    ("template_quota_pricing_tier", "free"),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert template_response.status_code == 303

        create_response = client.post(
            "/admin/users",
            content=urlencode(
                [
                    ("friendly_name", "Template User"),
                    ("email", "template@example.com"),
                    ("description", "Uses template"),
                    ("prefix", "templated"),
                    ("custom_subkey", ""),
                    ("template_name", "team-standard"),
                    ("backend_id", "secondary"),
                    ("quota_model", "gpt-4o"),
                    ("quota_requests", "5"),
                    ("quota_tokens", ""),
                    ("quota_pricing_tier", "payg"),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert create_response.status_code == 303

        policies_page = client.get("/admin/policies")
        assert policies_page.status_code == 200
        assert "Global defaults for all users" in policies_page.text
        assert "team-standard" in policies_page.text

    stored_quotas = json.loads(quota_file.read_text(encoding="utf-8"))
    assert stored_quotas["_global"]["*"]["requests"] == 250
    assert stored_quotas["_templates"]["team-standard"]["rules"]["*"]["total_tokens"] == 5000
    user_key = next(iter(stored_quotas["_users"].keys()))
    assert stored_quotas["_users"][user_key]["template"] == "team-standard"
    assert stored_quotas["_users"][user_key]["backend_id"] == "secondary"
    assert stored_quotas["_users"][user_key]["rules"]["gpt-4o"]["requests"] == 5


def test_admin_can_create_and_update_backends(tmp_path: Path, monkeypatch):
    quota_db = tmp_path / "quota.db"
    backend_file = tmp_path / "backends.json"
    monkeypatch.delenv("CIRCUIT_BACKENDS_JSON", raising=False)
    monkeypatch.setenv("CIRCUIT_BACKENDS_JSON_PATH", str(backend_file))

    app = create_app(
        config=_make_test_config(
            quota_db_path=str(quota_db),
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
            },
        )
    )
    with TestClient(app) as client:
        page = client.get("/admin/backends")
        assert page.status_code == 200
        assert "Create an upstream credential set" in page.text
        assert "Current default backend" in page.text

        create_response = client.post(
            "/admin/backends",
            content=urlencode(
                [
                    ("backend_id", "team-b"),
                    ("client_id", "client-b"),
                    ("client_secret", "secret-b"),
                    ("appkey", "appkey-b"),
                    ("token_url", "https://example.invalid/token-b"),
                    ("circuit_base", "https://example.invalid/b"),
                    ("api_version", "2025-05-01-preview"),
                    ("make_default", "1"),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert create_response.status_code == 303

        update_response = client.post(
            "/admin/backends/team-b",
            content=urlencode(
                [
                    ("client_id", "client-b2"),
                    ("client_secret", "secret-b2"),
                    ("appkey", "appkey-b2"),
                    ("token_url", "https://example.invalid/token-b2"),
                    ("circuit_base", "https://example.invalid/b2"),
                    ("api_version", ""),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert update_response.status_code == 303

        users_page = client.get("/admin/users")
        assert users_page.status_code == 200
        assert "team-b (default)" in users_page.text

    stored_backends = json.loads(backend_file.read_text(encoding="utf-8"))
    assert stored_backends["_default_backend"] == "team-b"
    assert stored_backends["backends"]["team-b"]["client_id"] == "client-b2"
    assert stored_backends["backends"]["team-b"]["circuit_base"] == "https://example.invalid/b2"
    assert stored_backends["backends"]["team-b"]["api_version"] == ""
    assert app.state.config.default_backend_id == "team-b"
    assert app.state.config.configured_backends()["team-b"].api_version == ""
