"""
Model pricing module for cost estimation.

Provides pricing tables and cost calculation functions for various LLM models
available through the Circuit API.

Pricing is based on OpenAI and public cloud AI pricing as of January 2026.
Update these values as Circuit pricing changes or new models are added.
"""
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger("oai_to_circuit.pricing")

# Model pricing per 1 million tokens (USD)
# Format: {"model_name": {"prompt": price_per_1M, "completion": price_per_1M}}
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # GPT-4 family
    "gpt-4o": {
        "prompt": 2.50,
        "completion": 10.00,
    },
    "gpt-4o-mini": {
        "prompt": 0.15,
        "completion": 0.60,
    },
    "gpt-4.1": {
        "prompt": 2.50,
        "completion": 10.00,
    },
    "gpt-4": {
        "prompt": 30.00,
        "completion": 60.00,
    },
    "gpt-4-32k": {
        "prompt": 60.00,
        "completion": 120.00,
    },
    
    # GPT-3.5 family (legacy)
    "gpt-3.5-turbo": {
        "prompt": 0.50,
        "completion": 1.50,
    },
    "gpt-35-turbo": {
        "prompt": 0.50,
        "completion": 1.50,
    },
    "gpt-35-turbo-16k": {
        "prompt": 3.00,
        "completion": 4.00,
    },
    
    # O-series models (reasoning models, more expensive)
    "o3": {
        "prompt": 15.00,
        "completion": 60.00,
    },
    "o4-mini": {
        "prompt": 3.00,
        "completion": 12.00,
    },
    "o1": {
        "prompt": 15.00,
        "completion": 60.00,
    },
    "o1-mini": {
        "prompt": 3.00,
        "completion": 12.00,
    },
    
    # Gemini models (Google)
    "gemini-2.5-flash": {
        "prompt": 0.075,
        "completion": 0.30,
    },
    "gemini-2.5-pro": {
        "prompt": 1.25,
        "completion": 5.00,
    },
    "gemini-1.5-pro": {
        "prompt": 1.25,
        "completion": 5.00,
    },
    "gemini-1.5-flash": {
        "prompt": 0.075,
        "completion": 0.30,
    },
    
    # Claude models (Anthropic) - if available through Circuit
    "claude-3-opus": {
        "prompt": 15.00,
        "completion": 75.00,
    },
    "claude-opus-4": {
        "prompt": 15.00,
        "completion": 75.00,
    },
    "claude-3.5-sonnet": {
        "prompt": 3.00,
        "completion": 15.00,
    },
    "claude-3-sonnet": {
        "prompt": 3.00,
        "completion": 15.00,
    },
    "claude-3-haiku": {
        "prompt": 0.25,
        "completion": 1.25,
    },
}


def get_model_pricing(model: str) -> Optional[Dict[str, float]]:
    """
    Get pricing for a specific model.
    
    Args:
        model: Model name
        
    Returns:
        Dict with 'prompt' and 'completion' prices per 1M tokens, or None if not found
    """
    # Try exact match first
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    
    # Try case-insensitive match
    model_lower = model.lower()
    for known_model, pricing in MODEL_PRICING.items():
        if known_model.lower() == model_lower:
            return pricing
    
    # No match found
    return None


def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int
) -> Tuple[float, bool]:
    """
    Calculate the estimated cost for a request.
    
    Args:
        model: Model name used
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        
    Returns:
        Tuple of (cost in USD, pricing_known)
        - cost: Estimated cost in USD
        - pricing_known: True if pricing is known, False if estimated/unknown
    """
    pricing = get_model_pricing(model)
    
    if pricing is None:
        # Unknown model - log warning and return 0 cost
        logger.debug(f"[COST CALCULATION] Unknown model: {model}. Add pricing to pricing.py")
        return (0.0, False)
    
    # Calculate cost per million tokens
    prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
    completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
    total_cost = prompt_cost + completion_cost
    
    logger.debug(
        f"[COST CALCULATION] Model: {model}, "
        f"Tokens: {prompt_tokens}+{completion_tokens}, "
        f"Cost: ${total_cost:.6f} "
        f"(prompt=${prompt_cost:.6f}, completion=${completion_cost:.6f})"
    )
    
    return (total_cost, True)


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


def list_known_models() -> list[str]:
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

