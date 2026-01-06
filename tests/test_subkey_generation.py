"""Tests for subkey generation utility."""

import re
from generate_subkeys import generate_subkey, generate_batch


def test_generate_subkey_default_length():
    """Generated key should be 32 characters by default."""
    key = generate_subkey()
    assert len(key) == 32


def test_generate_subkey_custom_length():
    """Generated key should respect custom length."""
    key = generate_subkey(length=16)
    assert len(key) == 16


def test_generate_subkey_with_prefix():
    """Generated key should include prefix."""
    key = generate_subkey(prefix="team_alpha")
    assert key.startswith("team_alpha_")
    # prefix + underscore + 32 random chars
    assert len(key) == len("team_alpha_") + 32


def test_generate_subkey_prefix_auto_underscore():
    """Prefix without trailing underscore should get one added."""
    key = generate_subkey(prefix="user")
    assert key.startswith("user_")


def test_generate_subkey_uniqueness():
    """Each generated key should be unique."""
    keys = {generate_subkey() for _ in range(100)}
    assert len(keys) == 100  # All unique


def test_generate_subkey_safe_characters():
    """Generated keys should only contain URL-safe characters."""
    key = generate_subkey()
    # Should only contain alphanumeric, hyphen, underscore
    assert re.match(r'^[a-zA-Z0-9_-]+$', key)


def test_generate_batch_count():
    """Batch generation should produce correct count."""
    keys = generate_batch(count=5)
    assert len(keys) == 5


def test_generate_batch_uniqueness():
    """Batch should contain all unique keys."""
    keys = generate_batch(count=20)
    assert len(keys) == len(set(keys))


def test_generate_batch_with_prefix():
    """Batch with prefix should apply to all keys."""
    keys = generate_batch(count=3, prefix="test")
    assert all(k.startswith("test_") for k in keys)


def test_subkey_extraction_compatibility():
    """Generated keys should work with extract_subkey function."""
    from starlette.requests import Request
    from starlette.types import Scope
    from oai_to_circuit.app import extract_subkey
    
    # Generate a key
    key = generate_subkey(prefix="test")
    
    # Test with X-Bridge-Subkey header
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "query_string": b"",
        "headers": [(b"x-bridge-subkey", key.encode("latin-1"))],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 12000),
    }
    request = Request(scope)
    
    extracted = extract_subkey(request)
    assert extracted == key


def test_subkey_quota_manager_compatibility():
    """Generated keys should work with QuotaManager."""
    import tempfile
    from oai_to_circuit.quota import QuotaManager
    
    # Generate keys
    key1 = generate_subkey(prefix="user")
    key2 = generate_subkey(prefix="team")
    
    quotas = {
        key1: {"gpt-4o-mini": {"requests": 5}},
        key2: {"gpt-4o-mini": {"requests": 10}},
    }
    
    with tempfile.NamedTemporaryFile() as tf:
        qm = QuotaManager(db_path=tf.name, quotas=quotas)
        
        # Test key1
        assert qm.is_request_allowed(key1, "gpt-4o-mini") is True
        qm.record_usage(key1, "gpt-4o-mini", request_inc=5)
        assert qm.is_request_allowed(key1, "gpt-4o-mini") is False
        
        # Test key2
        assert qm.is_request_allowed(key2, "gpt-4o-mini") is True
        qm.record_usage(key2, "gpt-4o-mini", request_inc=5)
        assert qm.is_request_allowed(key2, "gpt-4o-mini") is True  # Still has 5 left

