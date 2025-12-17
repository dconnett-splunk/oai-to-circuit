import json

from oai_to_circuit.quota import load_quotas_from_env_or_file


def test_load_quotas_from_env(monkeypatch):
    quotas = {"sk": {"*": {"requests": 1}}}
    monkeypatch.setenv("QUOTAS_JSON", json.dumps(quotas))
    monkeypatch.delenv("QUOTAS_JSON_PATH", raising=False)
    assert load_quotas_from_env_or_file() == quotas


def test_load_quotas_from_file(tmp_path, monkeypatch):
    quotas = {"sk": {"gpt-4o-mini": {"requests": 2}}}
    p = tmp_path / "quotas.json"
    p.write_text(json.dumps(quotas), encoding="utf-8")
    monkeypatch.delenv("QUOTAS_JSON", raising=False)
    monkeypatch.setenv("QUOTAS_JSON_PATH", str(p))
    assert load_quotas_from_env_or_file() == quotas


def test_load_quotas_invalid_returns_empty(tmp_path, monkeypatch):
    p = tmp_path / "quotas.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.delenv("QUOTAS_JSON", raising=False)
    monkeypatch.setenv("QUOTAS_JSON_PATH", str(p))
    assert load_quotas_from_env_or_file() == {}


