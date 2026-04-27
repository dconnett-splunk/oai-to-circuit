import os
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional, Dict, Tuple


class QuotaManager:
    """
    Tracks usage per subkey and model, and enforces quotas.
    - Storage: SQLite (file path configurable via env)
    - Quotas: provided via in-memory dict (loaded from env/file by caller)
    """

    def __init__(self, db_path: str, quotas: Dict[str, Dict[str, Dict[str, Any]]]):
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS monthly_usage (
                    subkey TEXT NOT NULL,
                    model TEXT NOT NULL,
                    usage_month TEXT NOT NULL,
                    requests INTEGER NOT NULL DEFAULT 0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (subkey, model, usage_month)
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
            # Create key_lifecycle table for key rotation tracking
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS key_lifecycle (
                    subkey TEXT PRIMARY KEY,
                    user_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    revoked_at TIMESTAMP,
                    revoke_reason TEXT,
                    replaced_by TEXT,
                    replaces TEXT,
                    FOREIGN KEY (replaced_by) REFERENCES key_lifecycle(subkey),
                    FOREIGN KEY (replaces) REFERENCES key_lifecycle(subkey)
                )
                """
            )
            # Create indexes for key_lifecycle
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lifecycle_user_id 
                ON key_lifecycle(user_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lifecycle_status 
                ON key_lifecycle(status)
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

    def _get_limits(self, subkey: str, model: str) -> Dict[str, Any]:
        model_limits = (self.quotas.get(subkey) or {}).get(model) or {}
        wildcard_limits = (self.quotas.get(subkey) or {}).get("*") or {}
        combined: Dict[str, Any] = dict(wildcard_limits)
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

    def get_monthly_usage(self, subkey: str, model: str, usage_month: str) -> Tuple[int, int, int, int]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT requests, prompt_tokens, completion_tokens, total_tokens
                FROM monthly_usage
                WHERE subkey=? AND model=? AND usage_month=?
                """,
                (subkey, model, usage_month),
            )
            row = cur.fetchone()
            if not row:
                return 0, 0, 0, 0
            return int(row[0]), int(row[1]), int(row[2]), int(row[3])

    def get_pricing_tier(self, subkey: str, model: str) -> str:
        tier = self._get_limits(subkey, model).get("pricing_tier")
        if isinstance(tier, str):
            tier = tier.lower()
            if tier in {"auto", "free", "payg"}:
                return tier
        return "auto"

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

    def is_subkey_authorized(self, subkey: str) -> bool:
        """
        Check if a subkey is authorized and active (not revoked).
        
        Args:
            subkey: The subkey to check
            
        Returns:
            True if the subkey is authorized AND active, False otherwise
        """
        # Check if subkey is in quotas configuration
        in_quotas = subkey in self.quotas
        
        # Check if subkey exists in the database
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM subkey_names WHERE subkey=?",
                (subkey,),
            )
            count = cur.fetchone()[0]
            in_database = count > 0
            
            # If not in quotas or database, reject
            if not (in_quotas or in_database):
                return False
            
            # Check lifecycle status if table exists
            try:
                cur = conn.execute(
                    "SELECT status FROM key_lifecycle WHERE subkey=?",
                    (subkey,)
                )
                row = cur.fetchone()
                if row:
                    # If lifecycle record exists, check status
                    status = row[0]
                    if status != 'active':
                        return False  # Key is revoked or replaced
            except sqlite3.OperationalError:
                # key_lifecycle table doesn't exist yet, allow the request
                pass
            
            return True
    
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
    
    def get_name_and_email(self, subkey: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get the friendly name and email for a subkey.
        
        Args:
            subkey: The subkey to look up
            
        Returns:
            Tuple of (friendly_name, email) - either can be None if not found
        """
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT friendly_name, email FROM subkey_names WHERE subkey=?",
                (subkey,),
            )
            row = cur.fetchone()
            if not row:
                return None, None
            return row[0], row[1]

    def record_usage(
        self,
        subkey: str,
        model: str,
        request_inc: int = 1,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        usage_month: Optional[str] = None,
    ) -> None:
        usage_month = usage_month or datetime.now(timezone.utc).strftime("%Y-%m")
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
                conn.execute(
                    """
                    INSERT INTO monthly_usage (subkey, model, usage_month, requests, prompt_tokens, completion_tokens, total_tokens)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(subkey, model, usage_month) DO UPDATE SET
                        requests = requests + excluded.requests,
                        prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                        completion_tokens = completion_tokens + excluded.completion_tokens,
                        total_tokens = total_tokens + excluded.total_tokens
                    """,
                    (
                        subkey,
                        model,
                        usage_month,
                        max(0, request_inc),
                        max(0, prompt_tokens),
                        max(0, completion_tokens),
                        max(0, total_tokens),
                    ),
                )
                conn.commit()


def load_quotas_from_env_or_file() -> Dict[str, Dict[str, Dict[str, Any]]]:
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

