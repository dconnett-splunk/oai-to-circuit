import os

from oai_to_circuit.config import load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("CIRCUIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("CIRCUIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CIRCUIT_APPKEY", raising=False)
    monkeypatch.delenv("API_VERSION", raising=False)
    monkeypatch.delenv("QUOTA_DB_PATH", raising=False)
    monkeypatch.delenv("REQUIRE_SUBKEY", raising=False)

    cfg = load_config()
    assert cfg.circuit_client_id == ""
    assert cfg.circuit_client_secret == ""
    assert cfg.circuit_appkey == ""
    assert cfg.api_version == "2025-04-01-preview"
    assert cfg.quota_db_path == "quota.db"
    assert cfg.require_subkey is True


def test_load_config_require_subkey_parsing(monkeypatch):
    monkeypatch.setenv("REQUIRE_SUBKEY", "false")
    assert load_config().require_subkey is False

    monkeypatch.setenv("REQUIRE_SUBKEY", "0")
    assert load_config().require_subkey is False

    monkeypatch.setenv("REQUIRE_SUBKEY", "yes")
    assert load_config().require_subkey is True


