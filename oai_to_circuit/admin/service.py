import errno
import json
import os
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from oai_to_circuit.config import BackendConfig, BridgeConfig, serialize_backend_configs
from oai_to_circuit.quota import QuotaManager
from oai_to_circuit.quota_config import (
    QuotaConfig,
    merge_rule_sets,
    normalize_quota_config,
    normalize_rule_map,
    resolve_model_limits,
    resolve_user_rules,
    serialize_quota_config,
    template_usage_count,
)
from oai_to_circuit.subkeys import generate_subkey, is_valid_subkey


VALID_TEMPLATE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
VALID_BACKEND_CHARS = VALID_TEMPLATE_CHARS


@dataclass(frozen=True)
class MetricCard:
    label: str
    value: str
    detail: str


@dataclass(frozen=True)
class BarPoint:
    label: str
    value: int
    value_label: str
    height_pct: float


@dataclass(frozen=True)
class TrendPoint:
    label: str
    short_label: str
    value: int
    value_label: str
    x_pct: float
    y_pct: float
    is_current: bool


@dataclass(frozen=True)
class TrendAxisLabel:
    label: str
    x_pct: float


@dataclass(frozen=True)
class TrendChart:
    current_value: str
    current_period: str
    change_label: str
    change_detail: str
    change_tone: str
    peak_value: str
    peak_period: str
    span_label: str
    line_path: str
    area_path: str
    points: List[TrendPoint]
    x_labels: List[TrendAxisLabel]
    y_labels: List[str]
    aria_label: str


@dataclass(frozen=True)
class ProgressRow:
    label: str
    value: int
    value_label: str
    width_pct: float
    detail: str


@dataclass(frozen=True)
class StorageStatus:
    mode: str
    label: str
    path: Optional[str]
    writable: bool
    detail: str


@dataclass(frozen=True)
class UserSummary:
    subkey: str
    friendly_name: str
    email: str
    description: str
    status: str
    requests: int
    total_tokens: int
    model_count: int
    quota_label: str
    template_name: str
    backend_id: str


@dataclass(frozen=True)
class UsageRow:
    model: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    requests_limit: Optional[int]
    total_tokens_limit: Optional[int]
    request_progress: Optional[float]
    token_progress: Optional[float]


@dataclass(frozen=True)
class QuotaRuleRow:
    model: str
    requests: str
    total_tokens: str
    pricing_tier: str


@dataclass(frozen=True)
class TemplateSummary:
    name: str
    description: str
    applied_users: int
    quota_label: str
    quota_rows: List[QuotaRuleRow]


@dataclass(frozen=True)
class BackendSummary:
    backend_id: str
    client_id: str
    client_secret: str
    appkey: str
    token_url: str
    circuit_base: str
    api_version: str
    assigned_users: int
    is_default: bool
    source_label: str
    source_detail: str


@dataclass(frozen=True)
class UserDetail:
    subkey: str
    friendly_name: str
    email: str
    description: str
    status: str
    revoke_reason: str
    created_at: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    usage_rows: List[UsageRow]
    monthly_requests: List[BarPoint]
    monthly_tokens: List[BarPoint]
    effective_quota_rows: List[QuotaRuleRow]
    local_quota_rows: List[QuotaRuleRow]
    effective_quota_label: str
    local_quota_label: str
    template_name: str
    backend_id: str


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _format_number(value: int) -> str:
    return f"{int(value):,}"


def _format_compact_number(value: int) -> str:
    absolute = abs(int(value))
    sign = "-" if value < 0 else ""
    if absolute >= 1_000_000_000:
        formatted = f"{absolute / 1_000_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{sign}{formatted}B"
    if absolute >= 1_000_000:
        formatted = f"{absolute / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{sign}{formatted}M"
    if absolute >= 1_000:
        formatted = f"{absolute / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{sign}{formatted}k"
    return _format_number(value)


def _ratio(current: int, limit: Optional[int]) -> Optional[float]:
    if limit is None or limit <= 0:
        return None
    return min(100.0, round((current / limit) * 100.0, 1))


def _chart_points(rows: Sequence[Tuple[str, int]]) -> List[BarPoint]:
    if not rows:
        return []

    max_value = max(value for _, value in rows) or 1
    return [
        BarPoint(
            label=label,
            value=value,
            value_label=_format_number(value),
            height_pct=max(8.0, round((value / max_value) * 100.0, 1)) if value else 0.0,
        )
        for label, value in rows
    ]


def _progress_rows(rows: Sequence[Tuple[str, int]], *, detail_label: str) -> List[ProgressRow]:
    if not rows:
        return []

    max_value = max(value for _, value in rows) or 1
    return [
        ProgressRow(
            label=label,
            value=value,
            value_label=_format_number(value),
            width_pct=max(6.0, round((value / max_value) * 100.0, 1)) if value else 0.0,
            detail=f"{_format_number(value)} {detail_label}",
        )
        for label, value in rows
    ]


def _parse_usage_month(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y-%m")
    except ValueError:
        return None


def _month_index(value: datetime) -> int:
    return (value.year * 12) + value.month - 1


def _month_from_index(index: int) -> datetime:
    year, month_index = divmod(index, 12)
    return datetime(year, month_index + 1, 1)


def _format_usage_month_full(value: Optional[datetime], fallback: str) -> str:
    return value.strftime("%b %Y") if value else fallback


def _format_usage_month_short(value: Optional[datetime], fallback: str) -> str:
    return value.strftime("%b '%y") if value else fallback


def _expand_month_rows(rows: Sequence[Tuple[str, int]], *, limit: int = 12) -> List[Tuple[str, int]]:
    if not rows:
        return []

    parsed_rows: List[Tuple[datetime, int]] = []
    for label, value in rows:
        month = _parse_usage_month(label)
        if month is None:
            return list(rows)[-limit:]
        parsed_rows.append((month, value))

    values_by_month = {month.strftime("%Y-%m"): value for month, value in parsed_rows}
    start_index = _month_index(parsed_rows[0][0])
    end_index = _month_index(parsed_rows[-1][0])

    expanded = [
        (month.strftime("%Y-%m"), int(values_by_month.get(month.strftime("%Y-%m"), 0)))
        for index in range(start_index, end_index + 1)
        for month in [_month_from_index(index)]
    ]
    return expanded[-limit:]


def _trend_change(current_value: int, previous_period: str, previous_value: int) -> Tuple[str, str, str]:
    delta = current_value - previous_value
    if delta > 0:
        return f"+{_format_number(delta)}", f"vs {previous_period}", "up"
    if delta < 0:
        return f"-{_format_number(abs(delta))}", f"vs {previous_period}", "down"
    return "No change", f"vs {previous_period}", "flat"


def _trend_label_indices(point_count: int) -> List[int]:
    if point_count <= 4:
        return list(range(point_count))

    candidate_indices = {0, point_count // 3, (point_count * 2) // 3, point_count - 1}
    return sorted(candidate_indices)


def _trend_chart(rows: Sequence[Tuple[str, int]], *, series_label: str) -> Optional[TrendChart]:
    expanded_rows = _expand_month_rows(rows)
    if not expanded_rows:
        return None

    max_value = max(value for _, value in expanded_rows)
    plot_top = 12.0
    plot_bottom = 90.0
    if len(expanded_rows) == 1:
        x_positions = [50.0]
    else:
        x_positions = [
            round(6.0 + ((88.0 * index) / (len(expanded_rows) - 1)), 2)
            for index in range(len(expanded_rows))
        ]

    def _y_position(value: int) -> float:
        if max_value <= 0:
            return plot_bottom
        return round(plot_bottom - ((value / max_value) * (plot_bottom - plot_top)), 2)

    points: List[TrendPoint] = []
    for index, ((raw_label, value), x_pct) in enumerate(zip(expanded_rows, x_positions)):
        month = _parse_usage_month(raw_label)
        full_label = _format_usage_month_full(month, raw_label)
        short_label = _format_usage_month_short(month, raw_label)
        points.append(
            TrendPoint(
                label=full_label,
                short_label=short_label,
                value=value,
                value_label=_format_number(value),
                x_pct=x_pct,
                y_pct=_y_position(value),
                is_current=index == len(expanded_rows) - 1,
            )
        )

    if len(points) == 1:
        line_path = f"M 42 {points[0].y_pct} L 58 {points[0].y_pct}"
        area_path = f"M 42 {plot_bottom} L 42 {points[0].y_pct} L 58 {points[0].y_pct} L 58 {plot_bottom} Z"
    else:
        line_segments = " L ".join(f"{point.x_pct} {point.y_pct}" for point in points)
        line_path = f"M {line_segments}"
        area_path = (
            f"M {points[0].x_pct} {plot_bottom} L "
            + " L ".join(f"{point.x_pct} {point.y_pct}" for point in points)
            + f" L {points[-1].x_pct} {plot_bottom} Z"
        )

    current_point = points[-1]
    if len(points) > 1:
        change_label, change_detail, change_tone = _trend_change(
            current_point.value,
            points[-2].label,
            points[-2].value,
        )
    else:
        change_label, change_detail, change_tone = (
            "First month recorded",
            "No earlier month to compare.",
            "flat",
        )

    peak_point = max(points, key=lambda point: (point.value, point.label))
    if len(points) == 1:
        span_label = f"Showing {points[0].label} only"
    else:
        span_label = f"Span: {points[0].label} to {points[-1].label}"

    x_labels = [
        TrendAxisLabel(label=points[index].short_label, x_pct=points[index].x_pct)
        for index in _trend_label_indices(len(points))
    ]
    midpoint_value = int(round(max_value / 2.0))

    return TrendChart(
        current_value=current_point.value_label,
        current_period=current_point.label,
        change_label=change_label,
        change_detail=change_detail,
        change_tone=change_tone,
        peak_value=peak_point.value_label,
        peak_period=peak_point.label,
        span_label=span_label,
        line_path=line_path,
        area_path=area_path,
        points=points,
        x_labels=x_labels,
        y_labels=[
            _format_compact_number(max_value),
            _format_compact_number(midpoint_value),
            "0",
        ],
        aria_label=(
            f"{series_label} from {points[0].label} to {points[-1].label}. "
            f"Current month {current_point.value_label} in {current_point.label}. "
            f"Peak {peak_point.value_label} in {peak_point.label}."
        ),
    )


def _default_quota_label(quota_rules: Mapping[str, Mapping[str, Any]]) -> str:
    wildcard = quota_rules.get("*") or {}
    if not quota_rules:
        return "Unlimited access"
    if not wildcard:
        return f"{len(quota_rules)} model rule(s)"

    parts: List[str] = []
    if wildcard.get("requests") is not None:
        parts.append(f"{_format_number(int(wildcard['requests']))} req")
    if wildcard.get("total_tokens") is not None:
        parts.append(f"{_format_number(int(wildcard['total_tokens']))} tok")
    if not parts:
        parts.append("Wildcard rule")

    override_count = len([model for model in quota_rules if model != "*"])
    if override_count:
        parts.append(f"+{override_count} override(s)")
    return " / ".join(parts)


def _quota_rows_from_rules(quota_rules: Mapping[str, Mapping[str, Any]]) -> List[QuotaRuleRow]:
    rows = [
        QuotaRuleRow(
            model=model,
            requests="" if limits.get("requests") is None else str(limits.get("requests")),
            total_tokens="" if limits.get("total_tokens") is None else str(limits.get("total_tokens")),
            pricing_tier=str(limits.get("pricing_tier") or "auto"),
        )
        for model, limits in sorted(quota_rules.items(), key=lambda item: ("0" if item[0] == "*" else "1", item[0]))
    ]
    if not rows:
        rows.append(QuotaRuleRow(model="*", requests="", total_tokens="", pricing_tier="auto"))
    return rows


def _combined_limits(quota_rules: Mapping[str, Mapping[str, Any]], model: str) -> Tuple[Optional[int], Optional[int]]:
    merged = resolve_model_limits(quota_rules, model)
    requests_limit = merged.get("requests")
    tokens_limit = merged.get("total_tokens")
    return (
        int(requests_limit) if requests_limit is not None else None,
        int(tokens_limit) if tokens_limit is not None else None,
    )


def _template_options(config: QuotaConfig) -> List[Tuple[str, str]]:
    return [
        (name, str(entry.get("description") or ""))
        for name, entry in sorted(config["templates"].items())
    ]


def get_quota_storage_status() -> StorageStatus:
    inline_config = os.environ.get("QUOTAS_JSON", "").strip()
    if inline_config:
        return StorageStatus(
            mode="env",
            label="Runtime quotas",
            path=None,
            writable=False,
            detail="QUOTAS_JSON is set. Admin changes update the running process only and will be lost after restart.",
        )

    path = os.environ.get("QUOTAS_JSON_PATH", "quotas.json")
    return StorageStatus(
        mode="file",
        label="File-backed quotas",
        path=path,
        writable=True,
        detail=f"Quota edits are persisted to {path}.",
    )


def get_backend_storage_status() -> StorageStatus:
    inline_config = os.environ.get("CIRCUIT_BACKENDS_JSON", "").strip()
    if inline_config:
        return StorageStatus(
            mode="env",
            label="Runtime backends",
            path=None,
            writable=False,
            detail="CIRCUIT_BACKENDS_JSON is set. Backend edits update the running process only and will be lost after restart.",
        )

    path = os.environ.get("CIRCUIT_BACKENDS_JSON_PATH", "").strip()
    if not path:
        return StorageStatus(
            mode="runtime",
            label="Runtime backends",
            path=None,
            writable=False,
            detail="No CIRCUIT_BACKENDS_JSON_PATH is configured. Backend edits apply immediately but are not persisted across restarts.",
        )

    return StorageStatus(
        mode="file",
        label="File-backed backends",
        path=path,
        writable=True,
        detail=f"Backend edits are persisted to {path}.",
    )


def build_overview_context(quota_manager: QuotaManager) -> Dict[str, Any]:
    quota_config = quota_manager.snapshot_quota_config()
    with _connect(quota_manager.db_path) as conn:
        totals = conn.execute(
            """
            SELECT
                COALESCE(SUM(requests), 0) AS requests,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COUNT(DISTINCT subkey) AS users,
                COUNT(DISTINCT model) AS models
            FROM usage
            """
        ).fetchone()
        monthly = conn.execute(
            """
            SELECT usage_month, COALESCE(SUM(requests), 0) AS requests, COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM monthly_usage
            GROUP BY usage_month
            ORDER BY usage_month ASC
            """
        ).fetchall()
        top_users_rows = conn.execute(
            """
            SELECT
                COALESCE(n.friendly_name, u.subkey) AS label,
                COALESCE(SUM(u.total_tokens), 0) AS total_tokens
            FROM usage u
            LEFT JOIN subkey_names n ON u.subkey = n.subkey
            GROUP BY u.subkey
            ORDER BY total_tokens DESC, label ASC
            LIMIT 6
            """
        ).fetchall()
        model_rows = conn.execute(
            """
            SELECT model, COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM usage
            GROUP BY model
            ORDER BY total_tokens DESC, model ASC
            LIMIT 6
            """
        ).fetchall()
        known_rows = conn.execute("SELECT subkey FROM subkey_names UNION SELECT subkey FROM key_lifecycle").fetchall()

    monthly_request_rows = [(row["usage_month"], int(row["requests"])) for row in monthly]
    monthly_token_rows = [(row["usage_month"], int(row["total_tokens"])) for row in monthly]
    request_trend = _trend_chart(monthly_request_rows, series_label="Monthly request totals")
    token_trend = _trend_chart(monthly_token_rows, series_label="Monthly token totals")
    top_users = _progress_rows([(row["label"], int(row["total_tokens"])) for row in top_users_rows], detail_label="tokens")
    top_models = _progress_rows([(row["model"], int(row["total_tokens"])) for row in model_rows], detail_label="tokens")

    managed_users = set(quota_config["users"].keys())
    managed_users.update(row["subkey"] for row in known_rows)

    metrics = [
        MetricCard("Total requests", _format_number(int(totals["requests"])), "All recorded requests"),
        MetricCard("Total tokens", _format_number(int(totals["total_tokens"])), "Prompt + completion across every user"),
        MetricCard("Tracked users", _format_number(len(managed_users)), "Users known from policy config or the admin database"),
        MetricCard("Active models", _format_number(int(totals["models"])), "Models with recorded usage"),
    ]

    return {
        "metrics": metrics,
        "request_trend": request_trend,
        "token_trend": token_trend,
        "top_users": top_users,
        "top_models": top_models,
        "storage": get_quota_storage_status(),
    }


def list_users_context(quota_manager: QuotaManager) -> Dict[str, Any]:
    quota_config = quota_manager.snapshot_quota_config()
    summaries: Dict[str, UserSummary] = {}

    with _connect(quota_manager.db_path) as conn:
        rows = conn.execute(
            """
            WITH known_subkeys AS (
                SELECT subkey FROM usage
                UNION
                SELECT subkey FROM subkey_names
                UNION
                SELECT subkey FROM key_lifecycle
            )
            SELECT
                k.subkey AS subkey,
                COALESCE(n.friendly_name, k.subkey) AS friendly_name,
                COALESCE(n.email, '') AS email,
                COALESCE(n.description, '') AS description,
                COALESCE(l.status, 'active') AS status,
                COALESCE(SUM(u.requests), 0) AS requests,
                COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
                COUNT(DISTINCT u.model) AS model_count
            FROM known_subkeys k
            LEFT JOIN subkey_names n ON k.subkey = n.subkey
            LEFT JOIN key_lifecycle l ON k.subkey = l.subkey
            LEFT JOIN usage u ON k.subkey = u.subkey
            GROUP BY k.subkey, n.friendly_name, n.email, n.description, l.status
            """
        ).fetchall()

    for row in rows:
        subkey = row["subkey"]
        user_entry = quota_config["users"].get(subkey) or {"template": "", "backend_id": "", "rules": {}}
        effective_rules = resolve_user_rules(quota_config, subkey)
        summaries[subkey] = UserSummary(
            subkey=subkey,
            friendly_name=row["friendly_name"],
            email=row["email"],
            description=row["description"],
            status=row["status"],
            requests=int(row["requests"]),
            total_tokens=int(row["total_tokens"]),
            model_count=int(row["model_count"]),
            quota_label=_default_quota_label(effective_rules),
            template_name=user_entry.get("template") or "",
            backend_id=user_entry.get("backend_id") or "",
        )

    for subkey, entry in quota_config["users"].items():
        summaries.setdefault(
            subkey,
            UserSummary(
                subkey=subkey,
                friendly_name=subkey,
                email="",
                description="",
                status="active",
                requests=0,
                total_tokens=0,
                model_count=0,
                quota_label=_default_quota_label(resolve_user_rules(quota_config, subkey)),
                template_name=entry.get("template") or "",
                backend_id=entry.get("backend_id") or "",
            ),
        )

    users = sorted(
        summaries.values(),
        key=lambda user: (-user.total_tokens, -user.requests, user.friendly_name.lower(), user.subkey.lower()),
    )
    return {
        "users": users,
        "storage": get_quota_storage_status(),
        "templates": _template_options(quota_config),
    }


def build_policies_context(quota_manager: QuotaManager) -> Dict[str, Any]:
    quota_config = quota_manager.snapshot_quota_config()
    global_rules = quota_config["global_rules"]
    templates = [
        TemplateSummary(
            name=name,
            description=str(entry.get("description") or ""),
            applied_users=template_usage_count(quota_config, name),
            quota_label=_default_quota_label(entry.get("rules") or {}),
            quota_rows=_quota_rows_from_rules(entry.get("rules") or {}),
        )
        for name, entry in sorted(quota_config["templates"].items())
    ]

    return {
        "global_quota_rows": _quota_rows_from_rules(global_rules),
        "templates": templates,
        "template_options": _template_options(quota_config),
    }


def build_backends_context(config: BridgeConfig, quota_manager: QuotaManager) -> Dict[str, Any]:
    quota_config = quota_manager.snapshot_quota_config()
    backend_storage = get_backend_storage_status()
    explicit_assignment_counts: Dict[str, int] = {}
    for entry in quota_config["users"].values():
        backend_id = str(entry.get("backend_id") or "").strip()
        if backend_id:
            explicit_assignment_counts[backend_id] = explicit_assignment_counts.get(backend_id, 0) + 1

    default_backend = config.default_backend()
    managed_target = Path(backend_storage.path).name if backend_storage.path else "backends.json"
    backends = [
        BackendSummary(
            backend_id=backend_id,
            client_id=backend.client_id,
            client_secret=backend.client_secret,
            appkey=backend.appkey,
            token_url=backend.token_url,
            circuit_base=backend.circuit_base,
            api_version=backend.api_version,
            assigned_users=explicit_assignment_counts.get(backend_id, 0),
            is_default=backend_id == config.default_backend_id,
            source_label=(
                "Bootstrap from credentials.env"
                if config.legacy_default_backend_active and backend_id == config.default_backend_id
                else (
                    f"Managed in {managed_target}"
                    if backend_storage.mode == "file"
                    else (
                        "Loaded from CIRCUIT_BACKENDS_JSON"
                        if backend_storage.mode == "env"
                        else "Runtime backend config"
                    )
                )
            ),
            source_detail=(
                "This backend is currently coming from CIRCUIT_CLIENT_ID, CIRCUIT_CLIENT_SECRET, and CIRCUIT_APPKEY in credentials.env. Saving or adding managed backends will write it into backends.json."
                if config.legacy_default_backend_active and backend_id == config.default_backend_id
                else (
                    "This backend is stored in the admin-managed backend file."
                    if backend_storage.mode == "file"
                    else (
                        "This backend came from the inline CIRCUIT_BACKENDS_JSON environment variable."
                        if backend_storage.mode == "env"
                        else "This backend exists only in the running process until you configure a persistent backend file."
                    )
                )
            ),
        )
        for backend_id, backend in sorted(config.configured_backends().items())
    ]
    return {
        "backends": backends,
        "backend_defaults": {
            "token_url": default_backend.token_url,
            "circuit_base": default_backend.circuit_base,
            "api_version": default_backend.api_version,
        },
        "backend_storage": backend_storage,
        "legacy_default_backend_active": config.legacy_default_backend_active,
    }


def get_user_detail(quota_manager: QuotaManager, subkey: str) -> Optional[UserDetail]:
    quota_config = quota_manager.snapshot_quota_config()
    user_entry = quota_config["users"].get(subkey) or {"template": "", "backend_id": "", "rules": {}}
    local_rules = normalize_rule_map(user_entry.get("rules"))
    effective_rules = resolve_user_rules(quota_config, subkey)

    with _connect(quota_manager.db_path) as conn:
        profile = conn.execute(
            """
            SELECT
                COALESCE(n.friendly_name, ?) AS friendly_name,
                COALESCE(n.email, '') AS email,
                COALESCE(n.description, '') AS description,
                COALESCE(n.created_at, '') AS created_at,
                COALESCE(l.status, 'active') AS status,
                COALESCE(l.revoke_reason, '') AS revoke_reason
            FROM (SELECT ? AS subkey) seed
            LEFT JOIN subkey_names n ON seed.subkey = n.subkey
            LEFT JOIN key_lifecycle l ON seed.subkey = l.subkey
            """,
            (subkey, subkey),
        ).fetchone()
        usage_totals = conn.execute(
            """
            SELECT
                COALESCE(SUM(requests), 0) AS requests,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM usage
            WHERE subkey=?
            """,
            (subkey,),
        ).fetchone()
        usage_rows = conn.execute(
            """
            SELECT model, requests, prompt_tokens, completion_tokens, total_tokens
            FROM usage
            WHERE subkey=?
            ORDER BY total_tokens DESC, requests DESC, model ASC
            """,
            (subkey,),
        ).fetchall()
        monthly_rows = conn.execute(
            """
            SELECT usage_month, COALESCE(SUM(requests), 0) AS requests, COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM monthly_usage
            WHERE subkey=?
            GROUP BY usage_month
            ORDER BY usage_month ASC
            """,
            (subkey,),
        ).fetchall()
        known = conn.execute(
            "SELECT 1 FROM subkey_names WHERE subkey=? UNION SELECT 1 FROM usage WHERE subkey=? UNION SELECT 1 FROM key_lifecycle WHERE subkey=? LIMIT 1",
            (subkey, subkey, subkey),
        ).fetchone()

    if not known and subkey not in quota_config["users"]:
        return None

    usage_view: List[UsageRow] = []
    for row in usage_rows:
        requests_limit, total_tokens_limit = _combined_limits(effective_rules, row["model"])
        usage_view.append(
            UsageRow(
                model=row["model"],
                requests=int(row["requests"]),
                prompt_tokens=int(row["prompt_tokens"]),
                completion_tokens=int(row["completion_tokens"]),
                total_tokens=int(row["total_tokens"]),
                requests_limit=requests_limit,
                total_tokens_limit=total_tokens_limit,
                request_progress=_ratio(int(row["requests"]), requests_limit),
                token_progress=_ratio(int(row["total_tokens"]), total_tokens_limit),
            )
        )

    if not usage_view:
        for model in sorted(model for model in effective_rules if model != "*"):
            requests_limit, total_tokens_limit = _combined_limits(effective_rules, model)
            usage_view.append(
                UsageRow(
                    model=model,
                    requests=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    requests_limit=requests_limit,
                    total_tokens_limit=total_tokens_limit,
                    request_progress=_ratio(0, requests_limit),
                    token_progress=_ratio(0, total_tokens_limit),
                )
            )

    return UserDetail(
        subkey=subkey,
        friendly_name=profile["friendly_name"],
        email=profile["email"],
        description=profile["description"],
        status=profile["status"],
        revoke_reason=profile["revoke_reason"],
        created_at=profile["created_at"],
        requests=int(usage_totals["requests"]),
        prompt_tokens=int(usage_totals["prompt_tokens"]),
        completion_tokens=int(usage_totals["completion_tokens"]),
        total_tokens=int(usage_totals["total_tokens"]),
        usage_rows=usage_view,
        monthly_requests=_chart_points([(row["usage_month"], int(row["requests"])) for row in monthly_rows]),
        monthly_tokens=_chart_points([(row["usage_month"], int(row["total_tokens"])) for row in monthly_rows]),
        effective_quota_rows=_quota_rows_from_rules(effective_rules),
        local_quota_rows=_quota_rows_from_rules(local_rules),
        effective_quota_label=_default_quota_label(effective_rules),
        local_quota_label=_default_quota_label(local_rules),
        template_name=user_entry.get("template") or "",
        backend_id=user_entry.get("backend_id") or "",
    )


def parse_int_field(value: str) -> Optional[int]:
    cleaned = value.strip()
    if not cleaned:
        return None
    parsed = int(cleaned)
    if parsed < 0:
        raise ValueError("Quota values must be zero or greater.")
    return parsed


def parse_quota_rows_from_form(values: Mapping[str, List[str]], *, field_prefix: str = "quota") -> Dict[str, Dict[str, Any]]:
    models = values.get(f"{field_prefix}_model", [])
    request_limits = values.get(f"{field_prefix}_requests", [])
    token_limits = values.get(f"{field_prefix}_tokens", [])
    pricing_tiers = values.get(f"{field_prefix}_pricing_tier", [])

    rules: Dict[str, Dict[str, Any]] = {}
    total_rows = max(len(models), len(request_limits), len(token_limits), len(pricing_tiers))
    for index in range(total_rows):
        model = (models[index] if index < len(models) else "").strip()
        requests_value = request_limits[index] if index < len(request_limits) else ""
        tokens_value = token_limits[index] if index < len(token_limits) else ""
        pricing_value = (pricing_tiers[index] if index < len(pricing_tiers) else "").strip().lower()

        if not model and not requests_value.strip() and not tokens_value.strip():
            continue
        if not model:
            raise ValueError("Every quota rule needs a model name. Use * for the default rule.")

        limits: Dict[str, Any] = {}
        requests_limit = parse_int_field(requests_value)
        total_tokens_limit = parse_int_field(tokens_value)
        if requests_limit is not None:
            limits["requests"] = requests_limit
        if total_tokens_limit is not None:
            limits["total_tokens"] = total_tokens_limit
        if pricing_value in {"auto", "free", "payg"}:
            limits["pricing_tier"] = pricing_value

        rules[model] = limits

    return rules


def _valid_template_name(name: str) -> bool:
    return bool(name) and all(char in VALID_TEMPLATE_CHARS for char in name)


def _get_user_entry(config: QuotaConfig, subkey: str) -> Dict[str, Any]:
    return config["users"].get(subkey) or {"template": "", "backend_id": "", "rules": {}}


def _normalize_backend_id(backend_id: str, available_backend_ids: Sequence[str]) -> str:
    selected_backend_id = backend_id.strip()
    if selected_backend_id and selected_backend_id not in set(available_backend_ids):
        raise ValueError("Selected backend does not exist.")
    return selected_backend_id


def _valid_backend_id(backend_id: str) -> bool:
    return bool(backend_id) and all(char in VALID_BACKEND_CHARS for char in backend_id)


def _required_backend_field(value: str, *, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} is required.")
    return cleaned


def _build_backend_config_from_values(
    *,
    client_id: str,
    client_secret: str,
    appkey: str,
    token_url: str,
    circuit_base: str,
    api_version: str,
) -> BackendConfig:
    return BackendConfig(
        client_id=_required_backend_field(client_id, label="Client ID"),
        client_secret=_required_backend_field(client_secret, label="Client secret"),
        appkey=_required_backend_field(appkey, label="App key"),
        token_url=_required_backend_field(token_url, label="Token URL"),
        circuit_base=_required_backend_field(circuit_base, label="Circuit base URL"),
        api_version=api_version.strip(),
    )


def create_user(
    quota_manager: QuotaManager,
    *,
    friendly_name: str,
    email: str,
    description: str,
    custom_subkey: str,
    prefix: str,
    template_name: str,
    backend_id: str,
    available_backend_ids: Sequence[str],
    quota_rules: Dict[str, Dict[str, Any]],
) -> str:
    name = friendly_name.strip()
    if not name:
        raise ValueError("Friendly name is required.")

    quota_config = quota_manager.snapshot_quota_config()
    selected_template = template_name.strip()
    if selected_template and selected_template not in quota_config["templates"]:
        raise ValueError("Selected template does not exist.")
    selected_backend_id = _normalize_backend_id(backend_id, available_backend_ids)

    subkey = custom_subkey.strip()
    if not subkey:
        subkey = generate_unique_subkey(quota_manager, prefix=prefix)
    elif not is_valid_subkey(subkey):
        raise ValueError("Custom subkeys may only contain letters, numbers, hyphens, and underscores.")

    if is_subkey_known(quota_manager, subkey):
        raise ValueError("That subkey already exists.")

    quota_manager.upsert_subkey_profile(subkey, name, email.strip(), description.strip())
    quota_manager.set_subkey_status(subkey, "active")

    quota_config["users"][subkey] = {
        "template": selected_template,
        "backend_id": selected_backend_id,
        "rules": quota_rules,
    }
    persist_quotas(quota_manager, quota_config)
    return subkey


def update_user_profile(
    quota_manager: QuotaManager,
    *,
    subkey: str,
    friendly_name: str,
    email: str,
    description: str,
) -> None:
    name = friendly_name.strip()
    if not name:
        raise ValueError("Friendly name is required.")
    quota_manager.upsert_subkey_profile(subkey, name, email.strip(), description.strip())


def update_user_status(
    quota_manager: QuotaManager,
    *,
    subkey: str,
    status: str,
    revoke_reason: str,
) -> None:
    quota_manager.set_subkey_status(subkey, status, revoke_reason)


def update_user_policy(
    quota_manager: QuotaManager,
    *,
    subkey: str,
    template_name: str,
    backend_id: str,
    available_backend_ids: Sequence[str],
) -> None:
    quota_config = quota_manager.snapshot_quota_config()
    selected_template = template_name.strip()
    if selected_template and selected_template not in quota_config["templates"]:
        raise ValueError("Selected template does not exist.")
    selected_backend_id = _normalize_backend_id(backend_id, available_backend_ids)

    entry = dict(_get_user_entry(quota_config, subkey))
    entry["template"] = selected_template
    entry["backend_id"] = selected_backend_id
    quota_config["users"][subkey] = entry
    persist_quotas(quota_manager, quota_config)


def update_user_quotas(
    quota_manager: QuotaManager,
    *,
    subkey: str,
    quota_rules: Dict[str, Dict[str, Any]],
) -> None:
    quota_config = quota_manager.snapshot_quota_config()
    entry = dict(_get_user_entry(quota_config, subkey))
    entry["rules"] = quota_rules

    if entry.get("template") or entry.get("backend_id") or quota_rules:
        quota_config["users"][subkey] = entry
    else:
        quota_config["users"].pop(subkey, None)
    persist_quotas(quota_manager, quota_config)


def update_global_quotas(quota_manager: QuotaManager, *, quota_rules: Dict[str, Dict[str, Any]]) -> None:
    quota_config = quota_manager.snapshot_quota_config()
    quota_config["global_rules"] = quota_rules
    persist_quotas(quota_manager, quota_config)


def create_template(
    quota_manager: QuotaManager,
    *,
    name: str,
    description: str,
    quota_rules: Dict[str, Dict[str, Any]],
) -> None:
    template_name = name.strip()
    if not _valid_template_name(template_name):
        raise ValueError("Template name is required and may only contain letters, numbers, hyphens, and underscores.")

    quota_config = quota_manager.snapshot_quota_config()
    if template_name in quota_config["templates"]:
        raise ValueError("A template with that name already exists.")

    quota_config["templates"][template_name] = {
        "name": template_name,
        "description": description.strip(),
        "rules": quota_rules,
    }
    persist_quotas(quota_manager, quota_config)


def update_template(
    quota_manager: QuotaManager,
    *,
    template_name: str,
    description: str,
    quota_rules: Dict[str, Dict[str, Any]],
) -> None:
    quota_config = quota_manager.snapshot_quota_config()
    if template_name not in quota_config["templates"]:
        raise ValueError("Template does not exist.")

    quota_config["templates"][template_name] = {
        "name": template_name,
        "description": description.strip(),
        "rules": quota_rules,
    }
    persist_quotas(quota_manager, quota_config)


def delete_template(quota_manager: QuotaManager, *, template_name: str) -> None:
    quota_config = quota_manager.snapshot_quota_config()
    if template_name not in quota_config["templates"]:
        raise ValueError("Template does not exist.")

    usage_count = template_usage_count(quota_config, template_name)
    if usage_count:
        raise ValueError(f"Template '{template_name}' is still assigned to {usage_count} user(s). Reassign them first.")

    quota_config["templates"].pop(template_name, None)
    persist_quotas(quota_manager, quota_config)


def set_default_backend(config: BridgeConfig, *, backend_id: str) -> BridgeConfig:
    selected_backend_id = backend_id.strip()
    available_backends = config.configured_backends()
    if selected_backend_id not in available_backends:
        raise ValueError("Selected backend does not exist.")

    updated_config = replace(config, default_backend_id=selected_backend_id, backend_configs=available_backends)
    persist_backends(updated_config)
    return updated_config


def create_backend(
    config: BridgeConfig,
    *,
    backend_id: str,
    client_id: str,
    client_secret: str,
    appkey: str,
    token_url: str,
    circuit_base: str,
    api_version: str,
    make_default: bool,
) -> BridgeConfig:
    normalized_backend_id = backend_id.strip()
    if not _valid_backend_id(normalized_backend_id):
        raise ValueError("Backend ID is required and may only contain letters, numbers, hyphens, and underscores.")

    backend_configs = config.configured_backends()
    if normalized_backend_id in backend_configs:
        raise ValueError("A backend with that ID already exists.")

    backend_configs[normalized_backend_id] = _build_backend_config_from_values(
        client_id=client_id,
        client_secret=client_secret,
        appkey=appkey,
        token_url=token_url,
        circuit_base=circuit_base,
        api_version=api_version,
    )
    updated_config = replace(
        config,
        default_backend_id=normalized_backend_id if make_default else config.default_backend_id,
        backend_configs=backend_configs,
        legacy_default_backend_active=False,
    )
    persist_backends(updated_config)
    return updated_config


def update_backend(
    config: BridgeConfig,
    *,
    backend_id: str,
    client_id: str,
    client_secret: str,
    appkey: str,
    token_url: str,
    circuit_base: str,
    api_version: str,
) -> BridgeConfig:
    normalized_backend_id = backend_id.strip()
    backend_configs = config.configured_backends()
    if normalized_backend_id not in backend_configs:
        raise ValueError("Backend does not exist.")

    backend_configs[normalized_backend_id] = _build_backend_config_from_values(
        client_id=client_id,
        client_secret=client_secret,
        appkey=appkey,
        token_url=token_url,
        circuit_base=circuit_base,
        api_version=api_version,
    )
    updated_config = replace(config, backend_configs=backend_configs, legacy_default_backend_active=False)
    persist_backends(updated_config)
    return updated_config


def persist_quotas(quota_manager: QuotaManager, quotas: Dict[str, Any]) -> None:
    normalized = normalize_quota_config(quotas)
    storage = get_quota_storage_status()
    quota_manager.replace_quota_config(normalized)
    if storage.mode != "file" or not storage.path:
        return

    path = Path(storage.path)
    try:
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        payload = serialize_quota_config(normalized)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        raise ValueError(_storage_write_error("quotas", path, exc, setting_name="QUOTAS_JSON_PATH")) from exc


def persist_backends(config: BridgeConfig) -> None:
    storage = get_backend_storage_status()
    if storage.mode != "file" or not storage.path:
        return

    path = Path(storage.path)
    try:
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        payload = serialize_backend_configs(
            default_backend_id=config.default_backend_id,
            backend_configs=config.configured_backends(),
        )
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        raise ValueError(_storage_write_error("backends", path, exc, setting_name="CIRCUIT_BACKENDS_JSON_PATH")) from exc


def _storage_write_error(kind: str, path: Path, exc: OSError, *, setting_name: str) -> str:
    reason = exc.strerror or str(exc)
    if exc.errno in {errno.EROFS, errno.EACCES, errno.EPERM}:
        return (
            f"Could not save {kind}. The service cannot write {path}. "
            f"Check systemd sandboxing and file permissions for {setting_name}, or move it to a writable location."
        )
    return f"Could not save {kind} to {path}: {reason}"


def is_subkey_known(quota_manager: QuotaManager, subkey: str) -> bool:
    quota_config = quota_manager.snapshot_quota_config()
    if subkey in quota_config["users"]:
        return True

    with _connect(quota_manager.db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM (
                SELECT subkey FROM usage
                UNION
                SELECT subkey FROM subkey_names
                UNION
                SELECT subkey FROM key_lifecycle
            ) known
            WHERE subkey=?
            LIMIT 1
            """,
            (subkey,),
        ).fetchone()
    return row is not None


def generate_unique_subkey(quota_manager: QuotaManager, prefix: str) -> str:
    for _ in range(10):
        candidate = generate_subkey(prefix=prefix)
        if not is_subkey_known(quota_manager, candidate):
            return candidate
    raise ValueError("Failed to generate a unique subkey.")
