from pathlib import Path

from oai_to_circuit.config import load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("CIRCUIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("CIRCUIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CIRCUIT_APPKEY", raising=False)
    monkeypatch.delenv("API_VERSION", raising=False)
    monkeypatch.delenv("QUOTA_DB_PATH", raising=False)
    monkeypatch.delenv("REQUIRE_SUBKEY", raising=False)
    monkeypatch.delenv("SPLUNK_HEC_URL", raising=False)
    monkeypatch.delenv("SPLUNK_HEC_TOKEN", raising=False)
    monkeypatch.delenv("CIRCUIT_BACKENDS_JSON", raising=False)
    monkeypatch.delenv("CIRCUIT_DEFAULT_BACKEND", raising=False)

    cfg = load_config()
    assert cfg.circuit_client_id == ""
    assert cfg.circuit_client_secret == ""
    assert cfg.circuit_appkey == ""
    assert cfg.api_version == "2025-04-01-preview"
    assert cfg.quota_db_path == "quota.db"
    assert cfg.require_subkey is True
    assert cfg.splunk_hec_url == ""
    assert cfg.splunk_hec_token == ""
    assert cfg.splunk_source == "oai-to-circuit"
    assert cfg.splunk_sourcetype == "llm:usage"
    assert cfg.splunk_index == "main"
    assert cfg.default_backend_id == "default"
    assert set(cfg.configured_backends().keys()) == {"default"}


def test_load_config_require_subkey_parsing(monkeypatch):
    monkeypatch.setenv("REQUIRE_SUBKEY", "false")
    assert load_config().require_subkey is False

    monkeypatch.setenv("REQUIRE_SUBKEY", "0")
    assert load_config().require_subkey is False

    monkeypatch.setenv("REQUIRE_SUBKEY", "yes")
    assert load_config().require_subkey is True


def test_load_config_splunk_hec(monkeypatch):
    monkeypatch.setenv("SPLUNK_HEC_URL", "https://splunk.example.com:8088/services/collector/event")
    monkeypatch.setenv("SPLUNK_HEC_TOKEN", "test-token-abc123")
    monkeypatch.setenv("SPLUNK_SOURCE", "custom-source")
    monkeypatch.setenv("SPLUNK_SOURCETYPE", "custom:sourcetype")
    monkeypatch.setenv("SPLUNK_INDEX", "custom-index")

    cfg = load_config()
    assert cfg.splunk_hec_url == "https://splunk.example.com:8088/services/collector/event"
    assert cfg.splunk_hec_token == "test-token-abc123"
    assert cfg.splunk_source == "custom-source"
    assert cfg.splunk_sourcetype == "custom:sourcetype"
    assert cfg.splunk_index == "custom-index"


def test_load_config_multiple_backends(monkeypatch):
    monkeypatch.setenv(
        "CIRCUIT_BACKENDS_JSON",
        """
        {
          "primary": {"client_id": "id-a", "client_secret": "secret-a", "appkey": "app-a"},
          "secondary": {
            "client_id": "id-b",
            "client_secret": "secret-b",
            "appkey": "app-b",
            "api_version": "2025-05-01-preview"
          }
        }
        """,
    )
    monkeypatch.setenv("CIRCUIT_DEFAULT_BACKEND", "secondary")

    cfg = load_config()
    primary = cfg.configured_backends()["primary"]
    secondary = cfg.default_backend()

    assert cfg.default_backend_id == "secondary"
    assert primary.client_id == "id-a"
    assert primary.api_version == "2025-04-01-preview"
    assert secondary.client_id == "id-b"
    assert secondary.appkey == "app-b"
    assert secondary.api_version == "2025-05-01-preview"


def test_load_config_reads_backends_from_file(tmp_path: Path, monkeypatch):
    backend_file = tmp_path / "backends.json"
    backend_file.write_text(
        """
        {
          "_default_backend": "team-b",
          "backends": {
            "default": {"client_id": "id-a", "client_secret": "secret-a", "appkey": "app-a"},
            "team-b": {
              "client_id": "id-b",
              "client_secret": "secret-b",
              "appkey": "app-b",
              "circuit_base": "https://example.invalid/team-b"
            }
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.delenv("CIRCUIT_BACKENDS_JSON", raising=False)
    monkeypatch.delenv("CIRCUIT_DEFAULT_BACKEND", raising=False)
    monkeypatch.setenv("CIRCUIT_BACKENDS_JSON_PATH", str(backend_file))

    cfg = load_config()

    assert cfg.default_backend_id == "team-b"
    assert set(cfg.configured_backends().keys()) == {"default", "team-b"}
    assert cfg.default_backend().circuit_base == "https://example.invalid/team-b"


def test_load_config_preserves_blank_backend_api_version(tmp_path: Path, monkeypatch):
    backend_file = tmp_path / "backends.json"
    backend_file.write_text(
        """
        {
          "_default_backend": "team-b",
          "backends": {
            "team-b": {
              "client_id": "id-b",
              "client_secret": "secret-b",
              "appkey": "app-b",
              "api_version": ""
            }
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.delenv("CIRCUIT_BACKENDS_JSON", raising=False)
    monkeypatch.delenv("CIRCUIT_DEFAULT_BACKEND", raising=False)
    monkeypatch.setenv("CIRCUIT_BACKENDS_JSON_PATH", str(backend_file))

    cfg = load_config()

    assert cfg.default_backend_id == "team-b"
    assert cfg.default_backend().api_version == ""
