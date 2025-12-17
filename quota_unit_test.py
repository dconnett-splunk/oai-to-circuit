#!/usr/bin/env python3
"""
Minimal unit test for QuotaManager behavior.
Run: python quota_unit_test.py
"""

import os
import tempfile
from quota import QuotaManager


def main():
    quotas = {
        "tester": {
            "gpt-4o-mini": {"requests": 2, "total_tokens": 10},
            "*": {"requests": 5},
        }
    }

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        db_path = tf.name

    try:
        qm = QuotaManager(db_path=db_path, quotas=quotas)

        # Initially allowed
        assert qm.is_request_allowed("tester", "gpt-4o-mini") is True
        qm.record_usage("tester", "gpt-4o-mini", request_inc=1, total_tokens=3)

        # Second request still allowed within limits
        assert qm.is_request_allowed("tester", "gpt-4o-mini") is True
        qm.record_usage("tester", "gpt-4o-mini", request_inc=1, total_tokens=6)

        # Requests limit reached (2)
        assert qm.is_request_allowed("tester", "gpt-4o-mini") is False

        # Token limit check: adding 2 more tokens would exceed 10
        assert qm.will_exceed_tokens("tester", "gpt-4o-mini", next_total_tokens=2) is True
        # Adding 1 token would not
        assert qm.will_exceed_tokens("tester", "gpt-4o-mini", next_total_tokens=1) is False

        print("QuotaManager unit tests: PASS")
    finally:
        try:
            os.unlink(db_path)
        except Exception:
            pass


if __name__ == "__main__":
    main()


