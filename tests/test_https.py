import ssl
from types import SimpleNamespace

import pytest


def test_build_app_import_string():
    # Light sanity check: uvicorn should be able to import this.
    from oai_to_circuit.server import build_app_import_string

    assert build_app_import_string() == "oai_to_circuit.server:app"


def test_server_ssl_missing_files_raises_systemexit(monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import server as server_mod

    monkeypatch.setattr(server_mod.os.path, "exists", lambda p: False)
    with pytest.raises(SystemExit) as exc:
        server_mod.main(["--ssl-only", "--cert", "missing.pem", "--key", "missing.key"])
    assert "SSL certificate files not found" in str(exc.value)


def test_server_ssl_only_passes_ssl_args_to_uvicorn(monkeypatch: pytest.MonkeyPatch):
    from oai_to_circuit import server as server_mod

    # Pretend cert/key exist, and skip real cert loading.
    monkeypatch.setattr(server_mod.os.path, "exists", lambda p: True)

    fake_ctx = SimpleNamespace(load_cert_chain=lambda cert, key: None)
    monkeypatch.setattr(server_mod.ssl, "create_default_context", lambda purpose: fake_ctx)

    captured: dict = {}

    def _fake_run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)
        return None

    monkeypatch.setattr(server_mod.uvicorn, "run", _fake_run)

    server_mod.main(
        [
            "--ssl-only",
            "--host",
            "127.0.0.1",
            "--ssl-port",
            "12443",
            "--cert",
            "cert.pem",
            "--key",
            "key.pem",
            "--no-reload",
        ]
    )

    assert captured["app"] == "oai_to_circuit.server:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 12443
    assert captured["ssl_keyfile"] == "key.pem"
    assert captured["ssl_certfile"] == "cert.pem"
    assert captured["reload"] is False

