import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from oai_to_circuit.app import create_app
from oai_to_circuit.config import BridgeConfig


def _make_test_config(
    *,
    quota_db_path: str,
    admin_password: str = "",
    admin_username: str = "admin",
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

        detail = client.get("/admin/users/sk-alpha")
        assert detail.status_code == 200
        assert "Observed activity and current limits" in detail.text
        assert "gpt-4o-mini" in detail.text
        assert "Primary admin user" in detail.text


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
