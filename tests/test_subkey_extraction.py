from starlette.requests import Request
from starlette.types import Scope

from oai_to_circuit.app import extract_subkey


def _make_request(headers: dict[str, str]) -> Request:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 12000),
    }
    return Request(scope)


def test_extract_subkey_prefers_header():
    r = _make_request({"X-Bridge-Subkey": "abc", "Authorization": "Bearer def"})
    assert extract_subkey(r) == "abc"


def test_extract_subkey_falls_back_to_authorization_bearer():
    r = _make_request({"Authorization": "Bearer def"})
    assert extract_subkey(r) == "def"


def test_extract_subkey_none_when_missing():
    r = _make_request({})
    assert extract_subkey(r) is None


