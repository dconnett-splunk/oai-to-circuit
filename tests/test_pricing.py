import pytest

from oai_to_circuit.pricing import calculate_cost, estimate_billing, get_model_pricing, list_known_models


def test_new_model_catalog_entries_are_known():
    for model in [
        "gpt-4.1-mini",
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1",
        "o4-mini",
        "o3",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gpt-5-chat",
        "gpt-5-nano",
        "gpt-5",
        "gpt-5-mini",
        "claude-sonnet-4-5",
        "claude-sonnet-4",
        "claude-opus-4-1",
        "claude-opus-4-5",
        "claude-haiku-4-5",
    ]:
        assert get_model_pricing(model) is not None


def test_legacy_aliases_resolve_to_canonical_pricing():
    assert get_model_pricing("gpt-o4-mini") == get_model_pricing("o4-mini")
    assert get_model_pricing("gpt-o3") == get_model_pricing("o3")
    assert get_model_pricing("gemini-2.5-pro-exp") == get_model_pricing("gemini-2.5-pro")
    assert get_model_pricing("claude-sonnet-4.5") == get_model_pricing("claude-sonnet-4-5")
    assert get_model_pricing("claude-opus-4.1") == get_model_pricing("claude-opus-4-1")
    assert get_model_pricing("claude-haiku-4.5") == get_model_pricing("claude-haiku-4-5")


def test_gemini_threshold_pricing_uses_higher_rates_for_large_prompts():
    small_cost, small_known = calculate_cost(
        "gemini-2.5-pro",
        prompt_tokens=150_000,
        completion_tokens=50_000,
    )
    large_cost, large_known = calculate_cost(
        "gemini-2.5-pro",
        prompt_tokens=250_000,
        completion_tokens=50_000,
    )

    assert small_known is True
    assert large_known is True
    assert small_cost == pytest.approx((150_000 / 1_000_000 * 1.25) + (50_000 / 1_000_000 * 10.00))
    assert large_cost == pytest.approx((250_000 / 1_000_000 * 2.50) + (50_000 / 1_000_000 * 15.00))


def test_web_search_models_include_request_surcharge():
    cost, known = calculate_cost(
        "gemini-2.5-pro-web-search",
        prompt_tokens=100_000,
        completion_tokens=50_000,
    )

    assert known is True
    assert cost == pytest.approx(
        (100_000 / 1_000_000 * 1.25)
        + (50_000 / 1_000_000 * 10.00)
        + (1 / 1000 * 35.00)
    )


def test_list_known_models_includes_new_deployments():
    known_models = list_known_models()

    assert "gpt-5" in known_models
    assert "gpt-5-chat" in known_models
    assert "gemini-3.1-flash-lite" in known_models
    assert "claude-opus-4-6" in known_models


def test_free_tier_models_apply_included_monthly_allowances():
    billing = estimate_billing(
        "gpt-5-nano",
        prompt_tokens=2_000,
        completion_tokens=500,
        month_prompt_tokens_used=0,
        month_completion_tokens_used=0,
    )

    assert billing["pricing_known"] is True
    assert billing["pricing_tier"] == "free"
    assert billing["estimated_cost_usd"] == pytest.approx(0.0)
    assert billing["estimated_payg_cost_usd"] > 0
    assert billing["free_prompt_tokens_applied"] == 2_000
    assert billing["free_completion_tokens_applied"] == 500
    assert billing["billable_prompt_tokens"] == 0
    assert billing["billable_completion_tokens"] == 0


def test_free_tier_models_bill_only_overage_tokens():
    billing = estimate_billing(
        "gpt-5-nano",
        prompt_tokens=10,
        completion_tokens=20,
        month_prompt_tokens_used=50_000_000 - 4,
        month_completion_tokens_used=5_000_000 - 7,
    )

    assert billing["pricing_tier"] == "blended"
    assert billing["free_prompt_tokens_applied"] == 4
    assert billing["free_completion_tokens_applied"] == 7
    assert billing["billable_prompt_tokens"] == 6
    assert billing["billable_completion_tokens"] == 13
    assert billing["estimated_cost_usd"] == pytest.approx(
        (6 / 1_000_000 * 0.055) + (13 / 1_000_000 * 0.44)
    )
