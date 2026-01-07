import os
from dataclasses import dataclass


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


def load_config() -> BridgeConfig:
    return BridgeConfig(
        circuit_client_id=os.environ.get("CIRCUIT_CLIENT_ID", ""),
        circuit_client_secret=os.environ.get("CIRCUIT_CLIENT_SECRET", ""),
        circuit_appkey=os.environ.get("CIRCUIT_APPKEY", ""),
        token_url="https://id.cisco.com/oauth2/default/v1/token",
        circuit_base="https://chat-ai.cisco.com",
        api_version=os.environ.get("API_VERSION", "2025-04-01-preview"),
        quota_db_path=os.environ.get("QUOTA_DB_PATH", "quota.db"),
        require_subkey=os.environ.get("REQUIRE_SUBKEY", "true").lower() in ("1", "true", "yes"),
        splunk_hec_url=os.environ.get("SPLUNK_HEC_URL", ""),
        splunk_hec_token=os.environ.get("SPLUNK_HEC_TOKEN", ""),
        splunk_source=os.environ.get("SPLUNK_SOURCE", "oai-to-circuit"),
        splunk_sourcetype=os.environ.get("SPLUNK_SOURCETYPE", "llm:usage"),
        splunk_index=os.environ.get("SPLUNK_INDEX", "oai_circuit"),
        splunk_verify_ssl=os.environ.get("SPLUNK_VERIFY_SSL", "true").lower() in ("1", "true", "yes"),
    )


