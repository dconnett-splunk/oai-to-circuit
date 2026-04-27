from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping


@dataclass(frozen=True)
class BackendConfig:
    client_id: str
    client_secret: str
    appkey: str
    token_url: str
    circuit_base: str
    api_version: str


@dataclass(frozen=True)
class BridgeConfig:
    circuit_client_id: str
    circuit_client_secret: str
    circuit_appkey: str
    token_url: str
    circuit_base: str
    api_version: str

    quota_db_path: str
    require_subkey: bool

    # Splunk HEC configuration (optional)
    splunk_hec_url: str
    splunk_hec_token: str
    splunk_source: str
    splunk_sourcetype: str
    splunk_index: str
    splunk_verify_ssl: bool

    admin_username: str
    admin_password: str
    admin_title: str

    default_backend_id: str = "default"
    backend_configs: Dict[str, BackendConfig] = field(default_factory=dict)
    legacy_default_backend_active: bool = False

    def default_backend(self) -> BackendConfig:
        return self.configured_backends()[self.default_backend_id]

    def configured_backends(self) -> Dict[str, BackendConfig]:
        if self.backend_configs:
            return dict(self.backend_configs)
        default_backend_id = self.default_backend_id or "default"
        return {
            default_backend_id: BackendConfig(
                client_id=self.circuit_client_id,
                client_secret=self.circuit_client_secret,
                appkey=self.circuit_appkey,
                token_url=self.token_url,
                circuit_base=self.circuit_base,
                api_version=self.api_version,
            )
        }

    def resolve_backend(self, backend_id: str = "") -> tuple[str, BackendConfig]:
        backends = self.configured_backends()
        default_backend_id = self.default_backend_id or next(iter(backends), "default")
        resolved_backend_id = (backend_id or "").strip() or default_backend_id
        if resolved_backend_id not in backends:
            raise KeyError(resolved_backend_id)
        return resolved_backend_id, backends[resolved_backend_id]


def _coerce_backend_value(raw_value: object) -> str:
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def _build_backend_config(raw_entry: Mapping[str, object], *, defaults: BackendConfig) -> BackendConfig:
    api_version = defaults.api_version
    if "api_version" in raw_entry:
        api_version = _coerce_backend_value(raw_entry.get("api_version"))
    return BackendConfig(
        client_id=_coerce_backend_value(raw_entry.get("client_id") or raw_entry.get("circuit_client_id")) or defaults.client_id,
        client_secret=_coerce_backend_value(raw_entry.get("client_secret") or raw_entry.get("circuit_client_secret")) or defaults.client_secret,
        appkey=_coerce_backend_value(raw_entry.get("appkey") or raw_entry.get("circuit_appkey")) or defaults.appkey,
        token_url=_coerce_backend_value(raw_entry.get("token_url")) or defaults.token_url,
        circuit_base=_coerce_backend_value(raw_entry.get("circuit_base")) or defaults.circuit_base,
        api_version=api_version,
    )


def _load_backend_configs(
    *,
    raw_json: str,
    requested_default_backend_id: str,
    fallback_backend: BackendConfig,
) -> tuple[str, Dict[str, BackendConfig], bool]:
    if not raw_json:
        default_backend_id = requested_default_backend_id or "default"
        return default_backend_id, {default_backend_id: fallback_backend}, False

    try:
        payload = json.loads(raw_json)
    except Exception:
        default_backend_id = requested_default_backend_id or "default"
        return default_backend_id, {default_backend_id: fallback_backend}, False

    if not isinstance(payload, dict):
        default_backend_id = requested_default_backend_id or "default"
        return default_backend_id, {default_backend_id: fallback_backend}, False

    payload_default_backend_id = ""
    backend_payload = payload
    if "backends" in payload or "_default_backend" in payload or "default_backend_id" in payload:
        payload_default_backend_id = _coerce_backend_value(
            payload.get("_default_backend") or payload.get("default_backend_id")
        )
        nested_backends = payload.get("backends")
        backend_payload = nested_backends if isinstance(nested_backends, dict) else {}

    backends: Dict[str, BackendConfig] = {}
    for backend_id, raw_entry in backend_payload.items():
        if not isinstance(backend_id, str) or not isinstance(raw_entry, dict):
            continue
        normalized_backend_id = backend_id.strip()
        if not normalized_backend_id:
            continue
        backends[normalized_backend_id] = _build_backend_config(raw_entry, defaults=fallback_backend)

    if not backends:
        default_backend_id = requested_default_backend_id or "default"
        return default_backend_id, {default_backend_id: fallback_backend}, False

    default_backend_id = requested_default_backend_id.strip() or payload_default_backend_id
    if default_backend_id and default_backend_id in backends:
        return default_backend_id, backends, True
    if "default" in backends:
        return "default", backends, True
    return next(iter(backends)), backends, True


def serialize_backend_configs(
    *,
    default_backend_id: str,
    backend_configs: Mapping[str, BackendConfig],
) -> Dict[str, object]:
    serialized_backends = {
        backend_id: {
            "client_id": backend.client_id,
            "client_secret": backend.client_secret,
            "appkey": backend.appkey,
            "token_url": backend.token_url,
            "circuit_base": backend.circuit_base,
            "api_version": backend.api_version,
        }
        for backend_id, backend in sorted(backend_configs.items())
    }
    return {
        "_default_backend": default_backend_id.strip() or next(iter(serialized_backends), "default"),
        "backends": serialized_backends,
    }


def _load_backend_json_from_env_or_file() -> str:
    inline_backends = os.environ.get("CIRCUIT_BACKENDS_JSON", "").strip()
    if inline_backends:
        return inline_backends

    backend_path = os.environ.get("CIRCUIT_BACKENDS_JSON_PATH", "").strip()
    if not backend_path:
        return ""

    try:
        return Path(backend_path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def load_config() -> BridgeConfig:
    token_url = "https://id.cisco.com/oauth2/default/v1/token"
    circuit_base = "https://chat-ai.cisco.com"
    api_version = os.environ.get("API_VERSION", "2025-04-01-preview")
    circuit_client_id = os.environ.get("CIRCUIT_CLIENT_ID", "")
    circuit_client_secret = os.environ.get("CIRCUIT_CLIENT_SECRET", "")
    circuit_appkey = os.environ.get("CIRCUIT_APPKEY", "")

    fallback_backend = BackendConfig(
        client_id=circuit_client_id,
        client_secret=circuit_client_secret,
        appkey=circuit_appkey,
        token_url=token_url,
        circuit_base=circuit_base,
        api_version=api_version,
    )
    default_backend_id, backend_configs, has_managed_backends = _load_backend_configs(
        raw_json=_load_backend_json_from_env_or_file(),
        requested_default_backend_id=os.environ.get("CIRCUIT_DEFAULT_BACKEND", "").strip(),
        fallback_backend=fallback_backend,
    )

    return BridgeConfig(
        circuit_client_id=circuit_client_id,
        circuit_client_secret=circuit_client_secret,
        circuit_appkey=circuit_appkey,
        token_url=token_url,
        circuit_base=circuit_base,
        api_version=api_version,
        default_backend_id=default_backend_id,
        backend_configs=backend_configs,
        legacy_default_backend_active=not has_managed_backends,
        quota_db_path=os.environ.get("QUOTA_DB_PATH", "quota.db"),
        require_subkey=os.environ.get("REQUIRE_SUBKEY", "true").lower() in ("1", "true", "yes"),
        splunk_hec_url=os.environ.get("SPLUNK_HEC_URL", ""),
        splunk_hec_token=os.environ.get("SPLUNK_HEC_TOKEN", ""),
        splunk_source=os.environ.get("SPLUNK_SOURCE", "oai-to-circuit"),
        splunk_sourcetype=os.environ.get("SPLUNK_SOURCETYPE", "llm:usage"),
        splunk_index=os.environ.get("SPLUNK_INDEX", "main"),
        splunk_verify_ssl=os.environ.get("SPLUNK_VERIFY_SSL", "true").lower() in ("1", "true", "yes"),
        admin_username=os.environ.get("ADMIN_USERNAME", "admin"),
        admin_password=os.environ.get("ADMIN_PASSWORD", ""),
        admin_title=os.environ.get("ADMIN_TITLE", "Circuit Bridge Admin"),
    )
