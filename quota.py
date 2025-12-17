#!/usr/bin/env python3

import os
import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, Dict, Any, Tuple


class QuotaManager:
    """
    Tracks usage per subkey and model, and enforces quotas.
    - Storage: SQLite (file path configurable via env)
    - Quotas: provided via in-memory dict (loaded from env/file by caller)
    """

    def __init__(self, db_path: str, quotas: Dict[str, Dict[str, Dict[str, int]]]):
        self.db_path = db_path
        self.quotas = quotas or {}
        self._init_db()
        self._lock = threading.Lock()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage (
                    subkey TEXT NOT NULL,
                    model TEXT NOT NULL,
                    requests INTEGER NOT NULL DEFAULT 0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (subkey, model)
                )
                """
            )
            conn.commit()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            yield conn
        finally:
            conn.close()

    def _get_limits(self, subkey: str, model: str) -> Dict[str, Optional[int]]:
        """
        Returns dict with possible keys: requests, total_tokens, prompt_tokens, completion_tokens
        Missing keys mean 'no limit' for that metric.
        """
        model_limits = (self.quotas.get(subkey) or {}).get(model) or {}
        # Also allow wildcard model '*'
        wildcard_limits = (self.quotas.get(subkey) or {}).get("*") or {}
        combined = dict(wildcard_limits)
        combined.update(model_limits)
        return combined

    def _get_usage(self, subkey: str, model: str) -> Tuple[int, int, int, int]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT requests, prompt_tokens, completion_tokens, total_tokens FROM usage WHERE subkey=? AND model=?",
                (subkey, model),
            )
            row = cur.fetchone()
            if not row:
                return 0, 0, 0, 0
            return int(row[0]), int(row[1]), int(row[2]), int(row[3])

    def is_request_allowed(self, subkey: str, model: str) -> bool:
        """
        Checks request-count limit before making an upstream call.
        """
        limits = self._get_limits(subkey, model)
        requests_limit = limits.get("requests")
        if requests_limit is None:
            return True
        requests_used, _, _, _ = self._get_usage(subkey, model)
        return requests_used < int(requests_limit)

    def will_exceed_tokens(self, subkey: str, model: str, next_total_tokens: int) -> bool:
        """
        Predict if adding next_total_tokens would exceed total_tokens limit.
        If there is no token limit configured, returns False.
        """
        limits = self._get_limits(subkey, model)
        total_limit = limits.get("total_tokens")
        if total_limit is None:
            return False
        _, _, _, total_used = self._get_usage(subkey, model)
        return (total_used + max(0, next_total_tokens)) > int(total_limit)

    def record_usage(
        self,
        subkey: str,
        model: str,
        request_inc: int = 1,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """
        Records usage after the upstream call.
        """
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO usage (subkey, model, requests, prompt_tokens, completion_tokens, total_tokens)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(subkey, model) DO UPDATE SET
                        requests = requests + excluded.requests,
                        prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                        completion_tokens = completion_tokens + excluded.completion_tokens,
                        total_tokens = total_tokens + excluded.total_tokens
                    """,
                    (
                        subkey,
                        model,
                        max(0, request_inc),
                        max(0, prompt_tokens),
                        max(0, completion_tokens),
                        max(0, total_tokens),
                    ),
                )
                conn.commit()


def load_quotas_from_env_or_file() -> Dict[str, Dict[str, Dict[str, int]]]:
    """
    Loads quotas from either:
      - Environment variable QUOTAS_JSON (stringified JSON)
      - File path specified by QUOTAS_JSON_PATH (default: quotas.json) if present
    Shape:
    {
      "subkeyA": {
        "gpt-4o-mini": { "requests": 1000, "total_tokens": 500000 },
        "*": { "requests": 5000 }
      },
      "subkeyB": {
        "gpt-4o": { "total_tokens": 100000 }
      }
    }
    """
    quotas_str = os.environ.get("QUOTAS_JSON", "").strip()
    if quotas_str:
        try:
            return json.loads(quotas_str)
        except Exception:
            # Fall through to file load if env var is malformed
            pass

    path = os.environ.get("QUOTAS_JSON_PATH", "quotas.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


