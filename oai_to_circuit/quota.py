import os
import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, Dict, Tuple


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
            # Create subkey_names table for friendly name mapping
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS subkey_names (
                    subkey TEXT PRIMARY KEY,
                    friendly_name TEXT NOT NULL,
                    email TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Create index on friendly_name for faster lookups
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_friendly_name 
                ON subkey_names(friendly_name)
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
        model_limits = (self.quotas.get(subkey) or {}).get(model) or {}
        wildcard_limits = (self.quotas.get(subkey) or {}).get("*") or {}
        combined: Dict[str, Optional[int]] = dict(wildcard_limits)
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
        limits = self._get_limits(subkey, model)
        requests_limit = limits.get("requests")
        if requests_limit is None:
            return True
        requests_used, _, _, _ = self._get_usage(subkey, model)
        return requests_used < int(requests_limit)

    def will_exceed_tokens(self, subkey: str, model: str, next_total_tokens: int) -> bool:
        limits = self._get_limits(subkey, model)
        total_limit = limits.get("total_tokens")
        if total_limit is None:
            return False
        _, _, _, total_used = self._get_usage(subkey, model)
        return (total_used + max(0, next_total_tokens)) > int(total_limit)

    def get_friendly_name(self, subkey: str) -> Optional[str]:
        """
        Get the friendly name for a subkey.
        
        Args:
            subkey: The subkey to look up
            
        Returns:
            The friendly name if found, None otherwise
        """
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT friendly_name FROM subkey_names WHERE subkey=?",
                (subkey,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return row[0]

    def record_usage(
        self,
        subkey: str,
        model: str,
        request_inc: int = 1,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
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
    quotas_str = os.environ.get("QUOTAS_JSON", "").strip()
    if quotas_str:
        try:
            return json.loads(quotas_str)
        except Exception:
            pass

    path = os.environ.get("QUOTAS_JSON_PATH", "quotas.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


