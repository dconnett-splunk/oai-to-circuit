"""
Model pricing module for cost estimation.

Provides pricing tables and cost calculation functions for various LLM models
available through the Circuit API.

Pricing is based on the current model catalog and token pricing configured for
the bridge. Some Gemini models have prompt-size breakpoints, and web-search
variants include a per-request surcharge.
"""
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger("oai_to_circuit.pricing")

# Model pricing per 1 million tokens (USD).
# Optional fields:
# - prompt_threshold_tokens: switch to the "..._above_threshold" prices when the
#   prompt token count for a single request exceeds this threshold
# - request_surcharge_per_1k: additional request-based fee charged per 1000
#   requests for web-search variants
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Active GPT family
    "gpt-4o": {"prompt": 2.75, "completion": 11.00},
    "gpt-4o-mini": {
        "prompt": 0.165,
        "completion": 0.66,
        "free_tier_prompt_included": 500_000_000,
        "free_tier_completion_included": 50_000_000,
    },
    "gpt-4.1": {
        "prompt": 2.00,
        "completion": 8.00,
        "free_tier_prompt_included": 50_000_000,
        "free_tier_completion_included": 5_000_000,
    },
    "gpt-4.1-mini": {"prompt": 0.40, "completion": 1.60},
    "gpt-5": {"prompt": 1.375, "completion": 11.00},
    "gpt-5-2": {"prompt": 1.75, "completion": 14.00},
    "gpt-5-4": {"prompt": 2.50, "completion": 15.00},
    "gpt-5-4-mini": {"prompt": 0.75, "completion": 4.15},
    "gpt-5-4-nano": {"prompt": 0.20, "completion": 1.25},
    "gpt-5-mini": {"prompt": 0.25, "completion": 2.00},
    "gpt-5-nano": {
        "prompt": 0.055,
        "completion": 0.44,
        "free_tier_prompt_included": 50_000_000,
        "free_tier_completion_included": 5_000_000,
    },
    "gpt-5-chat": {"prompt": 1.25, "completion": 10.00},

    # Legacy GPT models kept for older events/backfills
    "gpt-4": {"prompt": 30.00, "completion": 60.00},
    "gpt-4-32k": {"prompt": 60.00, "completion": 120.00},
    "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
    "gpt-35-turbo": {"prompt": 0.50, "completion": 1.50},
    "gpt-35-turbo-16k": {"prompt": 3.00, "completion": 4.00},

    # O-series
    "o3": {"prompt": 2.00, "completion": 8.00},
    "o4-mini": {"prompt": 1.10, "completion": 4.40},
    "o1": {"prompt": 15.00, "completion": 60.00},
    "o1-mini": {"prompt": 3.00, "completion": 12.00},

    # Gemini
    "gemini-2.5-flash": {"prompt": 0.30, "completion": 2.50},
    "gemini-2.5-pro": {
        "prompt": 1.25,
        "completion": 10.00,
        "prompt_threshold_tokens": 200000,
        "prompt_above_threshold": 2.50,
        "completion_above_threshold": 15.00,
    },
    "gemini-3-flash": {"prompt": 0.50, "completion": 3.00},
    "gemini-3.1-flash-lite": {
        "prompt": 0.25,
        "completion": 1.50,
        "free_tier_prompt_included": 50_000_000,
        "free_tier_completion_included": 5_000_000,
    },
    "gemini-3.1-pro": {
        "prompt": 2.00,
        "completion": 12.00,
        "prompt_threshold_tokens": 200000,
        "prompt_above_threshold": 4.00,
        "completion_above_threshold": 18.00,
    },
    "gemini-2.5-pro-web-search": {
        "prompt": 1.25,
        "completion": 10.00,
        "prompt_threshold_tokens": 200000,
        "prompt_above_threshold": 2.50,
        "completion_above_threshold": 15.00,
        "request_surcharge_per_1k": 35.00,
    },
    "gemini-2.5-flash-web-search": {
        "prompt": 0.30,
        "completion": 2.50,
        "request_surcharge_per_1k": 25.00,
    },
    "gemini-3-pro-web-search": {
        "prompt": 2.00,
        "completion": 12.00,
        "prompt_threshold_tokens": 200000,
        "prompt_above_threshold": 4.00,
        "completion_above_threshold": 18.00,
        "request_surcharge_per_1k": 14.00,
    },
    "gemini-3.1-flash-lite-web-search": {
        "prompt": 0.25,
        "completion": 1.50,
        "request_surcharge_per_1k": 14.00,
    },
    "gemini-3.1-pro-web-search": {
        "prompt": 2.00,
        "completion": 12.00,
        "prompt_threshold_tokens": 200000,
        "prompt_above_threshold": 4.00,
        "completion_above_threshold": 18.00,
        "request_surcharge_per_1k": 14.00,
    },

    # Older Gemini names kept for compatibility
    "gemini-1.5-pro": {"prompt": 1.25, "completion": 5.00},
    "gemini-1.5-flash": {"prompt": 0.075, "completion": 0.30},

    # Claude
    "claude-sonnet-4": {"prompt": 6.00, "completion": 22.50},
    "claude-sonnet-4-5": {"prompt": 6.60, "completion": 24.75},
    "claude-opus-4-1": {"prompt": 15.00, "completion": 75.00},
    "claude-opus-4-5": {"prompt": 5.00, "completion": 25.00},
    "claude-opus-4-6": {"prompt": 5.00, "completion": 25.00},
    "claude-haiku-4-5": {"prompt": 1.10, "completion": 5.50},

    # Older Claude names kept for compatibility
    "claude-3-opus": {"prompt": 15.00, "completion": 75.00},
    "claude-opus-4": {"prompt": 15.00, "completion": 75.00},
    "claude-3.5-sonnet": {"prompt": 3.00, "completion": 15.00},
    "claude-3-sonnet": {"prompt": 3.00, "completion": 15.00},
    "claude-3-haiku": {"prompt": 0.25, "completion": 1.25},
}

MODEL_ALIASES: Dict[str, str] = {
    "gpt-o3": "o3",
    "gpt-o4-mini": "o4-mini",
    "gemini-2.5-pro-exp": "gemini-2.5-pro",
    "gemini-2.5-flash-preview": "gemini-2.5-flash",
    "claude-sonnet-4.5": "claude-sonnet-4-5",
    "claude-opus-4.1": "claude-opus-4-1",
    "claude-opus-4.5": "claude-opus-4-5",
    "claude-opus-4.6": "claude-opus-4-6",
    "claude-haiku-4.5": "claude-haiku-4-5",
}


def normalize_model_name(model: str) -> str:
    """Normalize model aliases to canonical deployment names."""
    model_lower = model.lower()
    return MODEL_ALIASES.get(model_lower, model_lower)


def get_model_pricing(model: str) -> Optional[Dict[str, float]]:
    """
    Get pricing for a specific model.
    
    Args:
        model: Model name
        
    Returns:
        Dict with 'prompt' and 'completion' prices per 1M tokens, or None if not found
    """
    return MODEL_PRICING.get(normalize_model_name(model))


def estimate_billing(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    request_count: int = 1,
    pricing_tier: str = "auto",
    month_prompt_tokens_used: int = 0,
    month_completion_tokens_used: int = 0,
) -> Dict[str, Any]:
    """
    Estimate request cost and billing metadata for analytics.

    The bridge supports an "auto" mode for models that have monthly free-tier
    allowances. In auto mode, included prompt/completion allowances are applied
    first and only overage tokens are billed at pay-as-you-use rates.
    """
    normalized_model = normalize_model_name(model)
    pricing = get_model_pricing(model)
    tier_mode = (pricing_tier or "auto").lower()
    if tier_mode not in {"auto", "free", "payg"}:
        tier_mode = "auto"

    if pricing is None:
        return {
            "pricing_known": False,
            "pricing_model": normalized_model,
            "pricing_tier_mode": tier_mode,
            "pricing_tier": "unknown",
            "free_tier_eligible": False,
            "free_tier_prompt_included": 0,
            "free_tier_completion_included": 0,
            "monthly_prompt_tokens_before_request": max(0, month_prompt_tokens_used),
            "monthly_completion_tokens_before_request": max(0, month_completion_tokens_used),
            "monthly_prompt_tokens_after_request": max(0, month_prompt_tokens_used) + max(0, prompt_tokens),
            "monthly_completion_tokens_after_request": max(0, month_completion_tokens_used) + max(0, completion_tokens),
            "free_prompt_tokens_applied": 0,
            "free_completion_tokens_applied": 0,
            "billable_prompt_tokens": max(0, prompt_tokens),
            "billable_completion_tokens": max(0, completion_tokens),
            "payg_prompt_rate_per_million": 0.0,
            "payg_completion_rate_per_million": 0.0,
            "request_surcharge_usd": 0.0,
            "estimated_payg_cost_usd": 0.0,
            "estimated_cost_usd": 0.0,
        }

    prompt_tokens = max(0, prompt_tokens)
    completion_tokens = max(0, completion_tokens)
    month_prompt_tokens_used = max(0, month_prompt_tokens_used)
    month_completion_tokens_used = max(0, month_completion_tokens_used)

    prompt_rate = pricing["prompt"]
    completion_rate = pricing["completion"]
    prompt_threshold_tokens = int(pricing.get("prompt_threshold_tokens", 0))
    if prompt_threshold_tokens and prompt_tokens > prompt_threshold_tokens:
        prompt_rate = pricing.get("prompt_above_threshold", prompt_rate)
        completion_rate = pricing.get("completion_above_threshold", completion_rate)

    free_tier_prompt_included = int(pricing.get("free_tier_prompt_included", 0))
    free_tier_completion_included = int(pricing.get("free_tier_completion_included", 0))
    free_tier_eligible = free_tier_prompt_included > 0 or free_tier_completion_included > 0
    apply_free_tier = tier_mode == "free" or (tier_mode == "auto" and free_tier_eligible)

    remaining_prompt_allowance = max(0, free_tier_prompt_included - month_prompt_tokens_used) if apply_free_tier else 0
    remaining_completion_allowance = max(0, free_tier_completion_included - month_completion_tokens_used) if apply_free_tier else 0

    free_prompt_tokens_applied = min(prompt_tokens, remaining_prompt_allowance)
    free_completion_tokens_applied = min(completion_tokens, remaining_completion_allowance)
    billable_prompt_tokens = prompt_tokens - free_prompt_tokens_applied
    billable_completion_tokens = completion_tokens - free_completion_tokens_applied

    request_surcharge_per_1k = pricing.get("request_surcharge_per_1k", 0.0)
    request_surcharge = (max(0, request_count) / 1000) * request_surcharge_per_1k

    estimated_payg_cost = (prompt_tokens / 1_000_000) * prompt_rate
    estimated_payg_cost += (completion_tokens / 1_000_000) * completion_rate
    estimated_payg_cost += request_surcharge

    estimated_cost = (billable_prompt_tokens / 1_000_000) * prompt_rate
    estimated_cost += (billable_completion_tokens / 1_000_000) * completion_rate
    estimated_cost += request_surcharge

    resolved_tier = "payg"
    if apply_free_tier:
        if billable_prompt_tokens == 0 and billable_completion_tokens == 0 and request_surcharge == 0:
            resolved_tier = "free"
        elif free_prompt_tokens_applied > 0 or free_completion_tokens_applied > 0:
            resolved_tier = "blended"

    return {
        "pricing_known": True,
        "pricing_model": normalized_model,
        "pricing_tier_mode": tier_mode,
        "pricing_tier": resolved_tier,
        "free_tier_eligible": free_tier_eligible,
        "free_tier_prompt_included": free_tier_prompt_included,
        "free_tier_completion_included": free_tier_completion_included,
        "monthly_prompt_tokens_before_request": month_prompt_tokens_used,
        "monthly_completion_tokens_before_request": month_completion_tokens_used,
        "monthly_prompt_tokens_after_request": month_prompt_tokens_used + prompt_tokens,
        "monthly_completion_tokens_after_request": month_completion_tokens_used + completion_tokens,
        "free_prompt_tokens_applied": free_prompt_tokens_applied,
        "free_completion_tokens_applied": free_completion_tokens_applied,
        "billable_prompt_tokens": billable_prompt_tokens,
        "billable_completion_tokens": billable_completion_tokens,
        "payg_prompt_rate_per_million": prompt_rate,
        "payg_completion_rate_per_million": completion_rate,
        "request_surcharge_usd": request_surcharge,
        "estimated_payg_cost_usd": estimated_payg_cost,
        "estimated_cost_usd": estimated_cost,
    }


def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    request_count: int = 1,
) -> Tuple[float, bool]:
    """
    Calculate the estimated cost for a request.
    
    Args:
        model: Model name used
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        request_count: Number of requests represented by the event
        
    Returns:
        Tuple of (cost in USD, pricing_known)
        - cost: Estimated cost in USD
        - pricing_known: True if pricing is known, False if estimated/unknown
    """
    billing = estimate_billing(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        request_count=request_count,
        pricing_tier="payg",
    )

    if not billing["pricing_known"]:
        logger.debug(f"[COST CALCULATION] Unknown model: {model}. Add pricing to pricing.py")
        return (0.0, False)

    logger.debug(
        f"[COST CALCULATION] Model: {model}, "
        f"Tokens: {prompt_tokens}+{completion_tokens}, "
        f"Cost: ${billing['estimated_cost_usd']:.6f} "
        f"(prompt_rate=${billing['payg_prompt_rate_per_million']}/1M, "
        f"completion_rate=${billing['payg_completion_rate_per_million']}/1M, "
        f"surcharge=${billing['request_surcharge_usd']:.6f})"
    )

    return (float(billing["estimated_cost_usd"]), True)


def format_cost(cost: float) -> str:
    """
    Format cost for display.
    
    Args:
        cost: Cost in USD
        
    Returns:
        Formatted cost string
    """
    if cost < 0.0001:
        return f"${cost:.8f}"
    elif cost < 0.01:
        return f"${cost:.6f}"
    elif cost < 1.0:
        return f"${cost:.4f}"
    else:
        return f"${cost:.2f}"


def list_known_models() -> List[str]:
    """
    Get list of all models with known pricing.
    
    Returns:
        List of model names
    """
    return sorted(MODEL_PRICING.keys())


def add_custom_pricing(model: str, prompt_price: float, completion_price: float) -> None:
    """
    Add or update pricing for a model at runtime.
    
    Args:
        model: Model name
        prompt_price: Price per 1M prompt tokens (USD)
        completion_price: Price per 1M completion tokens (USD)
    """
    MODEL_PRICING[model] = {
        "prompt": prompt_price,
        "completion": completion_price,
    }
    logger.info(
        f"[COST CALCULATION] Added/updated pricing for {model}: "
        f"prompt=${prompt_price}/1M, completion=${completion_price}/1M"
    )
