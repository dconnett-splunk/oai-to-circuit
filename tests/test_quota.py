import tempfile

from oai_to_circuit.quota import QuotaManager


def test_quota_manager_requests_and_tokens():
    quotas = {
        "tester": {
            "gpt-4o-mini": {"requests": 2, "total_tokens": 10},
            "*": {"requests": 5},
        }
    }

    with tempfile.NamedTemporaryFile() as tf:
        qm = QuotaManager(db_path=tf.name, quotas=quotas)

        assert qm.is_request_allowed("tester", "gpt-4o-mini") is True
        qm.record_usage("tester", "gpt-4o-mini", request_inc=1, total_tokens=3)

        assert qm.is_request_allowed("tester", "gpt-4o-mini") is True
        qm.record_usage("tester", "gpt-4o-mini", request_inc=1, total_tokens=6)

        assert qm.is_request_allowed("tester", "gpt-4o-mini") is False
        assert qm.will_exceed_tokens("tester", "gpt-4o-mini", next_total_tokens=2) is True
        assert qm.will_exceed_tokens("tester", "gpt-4o-mini", next_total_tokens=1) is False


def test_model_blacklisting():
    """Test that setting requests to 0 blocks access to expensive models."""
    quotas = {
        "team_member": {
            "claude-3-opus": {"requests": 0},  # Blacklisted - too expensive
            "claude-opus-4": {"requests": 0},  # Blacklisted - too expensive
            "claude-3.5-sonnet": {"requests": 0},  # Blacklisted - too expensive
            "gpt-4o-mini": {"requests": 100},  # Allowed
            "*": {"requests": 50},  # Default for other models
        }
    }

    with tempfile.NamedTemporaryFile() as tf:
        qm = QuotaManager(db_path=tf.name, quotas=quotas)

        # Blacklisted models are blocked immediately
        assert qm.is_request_allowed("team_member", "claude-3-opus") is False
        assert qm.is_request_allowed("team_member", "claude-opus-4") is False
        assert qm.is_request_allowed("team_member", "claude-3.5-sonnet") is False

        # Allowed models work fine
        assert qm.is_request_allowed("team_member", "gpt-4o-mini") is True
        assert qm.is_request_allowed("team_member", "gpt-3.5-turbo") is True  # Uses wildcard


def test_per_model_quotas_override_wildcard():
    """Test that specific model quotas override wildcard settings."""
    quotas = {
        "user1": {
            "*": {"requests": 100},  # Default: 100 requests for any model
            "gpt-4o": {"requests": 10},  # But only 10 for this specific expensive model
        }
    }

    with tempfile.NamedTemporaryFile() as tf:
        qm = QuotaManager(db_path=tf.name, quotas=quotas)

        # Specific model uses its own limit
        assert qm.is_request_allowed("user1", "gpt-4o") is True
        for _ in range(10):
            qm.record_usage("user1", "gpt-4o", request_inc=1)
        assert qm.is_request_allowed("user1", "gpt-4o") is False

        # Other models still use wildcard limit
        assert qm.is_request_allowed("user1", "gpt-4o-mini") is True


