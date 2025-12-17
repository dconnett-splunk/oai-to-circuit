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


