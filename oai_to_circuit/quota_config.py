from __future__ import annotations

import fnmatch
import re
from copy import deepcopy
from typing import Any, Dict, Optional


GLOBAL_RULES_KEY = "_global"
TEMPLATES_KEY = "_templates"
USERS_KEY = "_users"
SPECIAL_KEYS = {GLOBAL_RULES_KEY, TEMPLATES_KEY, USERS_KEY}
NORMALIZED_GLOBAL_RULES_KEY = "global_rules"
NORMALIZED_TEMPLATES_KEY = "templates"
NORMALIZED_USERS_KEY = "users"
VALID_PRICING_TIERS = {"auto", "free", "payg"}


QuotaRules = Dict[str, Dict[str, Any]]
QuotaConfig = Dict[str, Any]
REGEX_RULE_PREFIXES = ("re:", "regex:")


def empty_quota_config() -> QuotaConfig:
    return {
        NORMALIZED_GLOBAL_RULES_KEY: {},
        NORMALIZED_TEMPLATES_KEY: {},
        NORMALIZED_USERS_KEY: {},
    }


def _normalize_limits(limits: Any) -> Dict[str, Any]:
    if not isinstance(limits, dict):
        return {}

    normalized = deepcopy(limits)
    pricing_tier = normalized.get("pricing_tier")
    if isinstance(pricing_tier, str):
        tier = pricing_tier.strip().lower()
        if tier in VALID_PRICING_TIERS:
            normalized["pricing_tier"] = tier
        else:
            normalized.pop("pricing_tier", None)
    return normalized


def looks_like_rule_map(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not value:
        return True
    return all(isinstance(rule, dict) for rule in value.values())


def normalize_rule_map(rules: Any) -> QuotaRules:
    if not looks_like_rule_map(rules):
        return {}
    return {
        str(model): _normalize_limits(limits)
        for model, limits in rules.items()
        if isinstance(model, str) and isinstance(limits, dict)
    }


def merge_rule_sets(base_rules: QuotaRules, override_rules: QuotaRules) -> QuotaRules:
    merged: QuotaRules = deepcopy(base_rules)
    for model, limits in override_rules.items():
        existing_limits = merged.get(model) or {}
        combined = dict(existing_limits)
        combined.update(deepcopy(limits))
        merged[model] = combined
    return merged


def _is_regex_rule(model_rule: str) -> bool:
    lowered = model_rule.lower()
    return any(lowered.startswith(prefix) for prefix in REGEX_RULE_PREFIXES)


def _regex_pattern(model_rule: str) -> str:
    lowered = model_rule.lower()
    for prefix in REGEX_RULE_PREFIXES:
        if lowered.startswith(prefix):
            return model_rule[len(prefix):]
    return model_rule


def _is_glob_rule(model_rule: str) -> bool:
    return model_rule != "*" and any(char in model_rule for char in "*?[")


def _is_exact_rule(model_rule: str) -> bool:
    return model_rule != "*" and not _is_regex_rule(model_rule) and not _is_glob_rule(model_rule)


def _matches_model_rule(model_rule: str, model: str) -> bool:
    if model_rule == "*":
        return True
    if _is_regex_rule(model_rule):
        try:
            return re.fullmatch(_regex_pattern(model_rule), model) is not None
        except re.error:
            return False
    if _is_glob_rule(model_rule):
        return fnmatch.fnmatchcase(model, model_rule)
    return model_rule == model


def _pattern_specificity(model_rule: str) -> tuple[int, int, int, str]:
    if _is_regex_rule(model_rule):
        pattern = _regex_pattern(model_rule)
        literal_chars = sum(1 for char in pattern if char.isalnum() or char in "-_.")
        return (literal_chars, len(pattern), 1, model_rule)

    literal_chars = sum(1 for char in model_rule if char not in "*?[")
    return (literal_chars, len(model_rule), 0, model_rule)


def resolve_model_limits(quota_rules: Any, model: str) -> Dict[str, Any]:
    normalized_rules = normalize_rule_map(quota_rules)
    merged: Dict[str, Any] = dict(normalized_rules.get("*") or {})

    pattern_matches = sorted(
        (
            model_rule
            for model_rule in normalized_rules
            if not _is_exact_rule(model_rule) and model_rule != "*" and _matches_model_rule(model_rule, model)
        ),
        key=_pattern_specificity,
    )
    for model_rule in pattern_matches:
        merged.update(deepcopy(normalized_rules.get(model_rule) or {}))

    if model in normalized_rules:
        merged.update(deepcopy(normalized_rules.get(model) or {}))

    return merged


def _normalize_template_entry(name: str, entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    if "rules" in entry or "description" in entry:
        rules = normalize_rule_map(entry.get("rules"))
        description = str(entry.get("description") or "").strip()
    else:
        rules = normalize_rule_map(entry)
        description = ""

    return {"name": name, "description": description, "rules": rules}


def _normalize_user_entry(entry: Any) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        return {"template": "", "backend_id": "", "rules": {}}

    if "rules" in entry or "template" in entry or "backend_id" in entry or "backend" in entry:
        template_name = str(entry.get("template") or "").strip()
        backend_id = str(entry.get("backend_id") or entry.get("backend") or "").strip()
        rules = normalize_rule_map(entry.get("rules"))
    else:
        template_name = ""
        backend_id = ""
        rules = normalize_rule_map(entry)

    return {"template": template_name, "backend_id": backend_id, "rules": rules}


def normalize_quota_config(raw_config: Any) -> QuotaConfig:
    config = empty_quota_config()
    if not isinstance(raw_config, dict):
        return config

    if (
        NORMALIZED_GLOBAL_RULES_KEY in raw_config
        or NORMALIZED_TEMPLATES_KEY in raw_config
        or NORMALIZED_USERS_KEY in raw_config
    ):
        config[NORMALIZED_GLOBAL_RULES_KEY] = normalize_rule_map(raw_config.get(NORMALIZED_GLOBAL_RULES_KEY))

        raw_templates = raw_config.get(NORMALIZED_TEMPLATES_KEY)
        if isinstance(raw_templates, dict):
            for name, entry in raw_templates.items():
                if not isinstance(name, str):
                    continue
                normalized = _normalize_template_entry(name, entry)
                if normalized is not None:
                    config[NORMALIZED_TEMPLATES_KEY][name] = normalized

        raw_users = raw_config.get(NORMALIZED_USERS_KEY)
        if isinstance(raw_users, dict):
            for subkey, entry in raw_users.items():
                if isinstance(subkey, str):
                    config[NORMALIZED_USERS_KEY][subkey] = _normalize_user_entry(entry)

        return config

    config[NORMALIZED_GLOBAL_RULES_KEY] = normalize_rule_map(raw_config.get(GLOBAL_RULES_KEY))

    raw_templates = raw_config.get(TEMPLATES_KEY)
    if isinstance(raw_templates, dict):
        for name, entry in raw_templates.items():
            if not isinstance(name, str):
                continue
            normalized = _normalize_template_entry(name, entry)
            if normalized is not None:
                config[NORMALIZED_TEMPLATES_KEY][name] = normalized

    raw_users = raw_config.get(USERS_KEY)
    if isinstance(raw_users, dict):
        for subkey, entry in raw_users.items():
            if not isinstance(subkey, str):
                continue
            config[NORMALIZED_USERS_KEY][subkey] = _normalize_user_entry(entry)

    for key, value in raw_config.items():
        if key in SPECIAL_KEYS or not isinstance(key, str):
            continue

        legacy_entry = _normalize_user_entry(value)
        existing = config[NORMALIZED_USERS_KEY].get(key) or {"template": "", "backend_id": "", "rules": {}}
        config[NORMALIZED_USERS_KEY][key] = {
            "template": existing.get("template") or legacy_entry.get("template") or "",
            "backend_id": existing.get("backend_id") or legacy_entry.get("backend_id") or "",
            "rules": merge_rule_sets(existing.get("rules") or {}, legacy_entry.get("rules") or {}),
        }

    return config


def resolve_user_rules(config: QuotaConfig, subkey: str) -> QuotaRules:
    normalized = normalize_quota_config(config)
    user_entry = normalized[NORMALIZED_USERS_KEY].get(subkey) or {"template": "", "backend_id": "", "rules": {}}
    rules = normalize_rule_map(normalized[NORMALIZED_GLOBAL_RULES_KEY])

    template_name = user_entry.get("template") or ""
    template_entry = normalized[NORMALIZED_TEMPLATES_KEY].get(template_name) if template_name else None
    if template_entry:
        rules = merge_rule_sets(rules, template_entry.get("rules") or {})

    rules = merge_rule_sets(rules, user_entry.get("rules") or {})
    return rules


def resolve_user_backend(config: QuotaConfig, subkey: str) -> str:
    normalized = normalize_quota_config(config)
    user_entry = normalized[NORMALIZED_USERS_KEY].get(subkey) or {"template": "", "backend_id": "", "rules": {}}
    return str(user_entry.get("backend_id") or "").strip()


def build_effective_user_map(config: QuotaConfig) -> Dict[str, QuotaRules]:
    normalized = normalize_quota_config(config)
    return {
        subkey: resolve_user_rules(normalized, subkey)
        for subkey in normalized[NORMALIZED_USERS_KEY]
    }


def quota_config_uses_advanced_sections(config: QuotaConfig) -> bool:
    normalized = normalize_quota_config(config)
    if normalized[NORMALIZED_GLOBAL_RULES_KEY] or normalized[NORMALIZED_TEMPLATES_KEY]:
        return True
    return any(
        (entry.get("template") or "").strip() or (entry.get("backend_id") or "").strip()
        for entry in normalized[NORMALIZED_USERS_KEY].values()
    )


def serialize_quota_config(config: QuotaConfig) -> Dict[str, Any]:
    normalized = normalize_quota_config(config)

    if not quota_config_uses_advanced_sections(normalized):
        return {
            subkey: deepcopy(entry.get("rules") or {})
            for subkey, entry in normalized[NORMALIZED_USERS_KEY].items()
            if entry.get("rules") or subkey
        }

    payload: Dict[str, Any] = {}
    if normalized[NORMALIZED_GLOBAL_RULES_KEY]:
        payload[GLOBAL_RULES_KEY] = deepcopy(normalized[NORMALIZED_GLOBAL_RULES_KEY])

    if normalized[NORMALIZED_TEMPLATES_KEY]:
        payload[TEMPLATES_KEY] = {
            name: {
                "description": entry.get("description") or "",
                "rules": deepcopy(entry.get("rules") or {}),
            }
            for name, entry in sorted(normalized[NORMALIZED_TEMPLATES_KEY].items())
        }

    if normalized[NORMALIZED_USERS_KEY]:
        payload[USERS_KEY] = {}
        for subkey, entry in sorted(normalized[NORMALIZED_USERS_KEY].items()):
            template_name = (entry.get("template") or "").strip()
            backend_id = (entry.get("backend_id") or "").strip()
            rules = deepcopy(entry.get("rules") or {})
            if template_name or backend_id:
                user_entry: Dict[str, Any] = {"rules": rules}
                if template_name:
                    user_entry["template"] = template_name
                if backend_id:
                    user_entry["backend_id"] = backend_id
                payload[USERS_KEY][subkey] = user_entry
            else:
                payload[USERS_KEY][subkey] = rules

    return payload


def template_usage_count(config: QuotaConfig, template_name: str) -> int:
    normalized = normalize_quota_config(config)
    return sum(1 for entry in normalized[NORMALIZED_USERS_KEY].values() if (entry.get("template") or "") == template_name)
