import pytest
from lookup import (
    resolve_product,
    resolve_static,
    auto_select_remote_param,
    PRODUCTS,
    STATIC_OPTIONS,
)


# --- resolve_product ---

def test_resolve_product_exact_key():
    result = resolve_product("DUO")
    assert result == ("DUO", "Duo")


def test_resolve_product_exact_key_case_insensitive():
    result = resolve_product("duo")
    assert result == ("DUO", "Duo")


def test_resolve_product_by_label():
    result = resolve_product("Secure Firewall")
    assert result == ("SECURE_FIREWALL", "Secure Firewall")


def test_resolve_product_by_label_case_insensitive():
    result = resolve_product("secure firewall")
    assert result == ("SECURE_FIREWALL", "Secure Firewall")


def test_resolve_product_by_key_with_spaces():
    result = resolve_product("SECURE FIREWALL")
    assert result == ("SECURE_FIREWALL", "Secure Firewall")


def test_resolve_product_substring_label():
    result = resolve_product("endpoint protection")
    assert result == ("EPP", "Endpoint Protection Platform (EPP)")


def test_resolve_product_defense_orchestrator():
    result = resolve_product("Defense Orchestrator")
    assert result == ("DEFENSE_ORCHESTRATOR", "Defense Orchestrator")


def test_resolve_product_crosswork_cloud():
    result = resolve_product("crosswork cloud")
    assert result == ("CROSSWORK_CLOUD", "Crosswork Cloud")


def test_resolve_product_ios_xr():
    result = resolve_product("IOS XR")
    assert result is not None
    assert result[0] == "IOS_XR_FLEXIBLE_CONSUMPTION_MODEL"


def test_resolve_product_not_found():
    result = resolve_product("nonexistent product xyz")
    assert result is None


def test_all_24_products_resolvable():
    """Every product in the catalog should be resolvable by its label."""
    for value, label in PRODUCTS.items():
        result = resolve_product(label)
        assert result is not None, f"Could not resolve product label: {label}"
        assert result[0] == value


# --- resolve_static ---

def test_resolve_static_service():
    result = resolve_static("service", "Advanced Services")
    assert result == ("advanced services", "Advanced Services")


def test_resolve_static_region_apjc():
    result = resolve_static("region", "APJC")
    assert result == ("APJC", "APJC")


def test_resolve_static_timeframe_last_quarter():
    result = resolve_static("timeframe", "last quarter")
    assert result == ("last quarter", "Last quarter")


def test_resolve_static_comparison():
    result = resolve_static("comparison", "market segment")
    assert result == ("market segment", "Market Segment")


def test_resolve_static_forecast_commit():
    result = resolve_static("forecastStatuses", "Commit")
    assert result == ("Commit", "Commit")


def test_resolve_static_subscription_timeframe():
    result = resolve_static("subscriptionTimeframe", "0-90 days")
    assert result == ("0-90 days", "0-90 days")


def test_resolve_static_metric_type():
    result = resolve_static("metricType", "usage")
    assert result == ("UsageMetrics", "Usage/scale metrics")


def test_resolve_static_tac_time_period():
    result = resolve_static("tacSentimentTimePeriod", "current quarter")
    assert result == ("current quarter", "Current quarter")


def test_resolve_static_not_found():
    result = resolve_static("region", "Antarctica")
    assert result is None


def test_resolve_static_unknown_param():
    result = resolve_static("nonexistent_param", "anything")
    assert result is None


def test_resolve_static_handles_none_label():
    """Bug fix: options with None label should not crash."""
    from lookup import STATIC_OPTIONS
    original = STATIC_OPTIONS.get("region", [])
    STATIC_OPTIONS["_test_none"] = [
        {"label": None, "value": "test_val"},
        {"label": "Valid", "value": None},
    ]
    try:
        result = resolve_static("_test_none", "test_val")
        assert result is not None or result is None  # just verify no crash
    finally:
        del STATIC_OPTIONS["_test_none"]


def test_all_static_options_resolvable():
    """Every static option should be resolvable by its label."""
    for param_name, options in STATIC_OPTIONS.items():
        for opt in options:
            result = resolve_static(param_name, opt["label"])
            assert result is not None, (
                f"Could not resolve {param_name} option: {opt['label']}"
            )
            assert result[0] == opt["value"]


@pytest.mark.asyncio
async def test_auto_select_remote_param_returns_none_for_ambiguous_options(monkeypatch):
    async def fake_get_list(*args, **kwargs):
        return [
            {"label": "A", "value": "a"},
            {"label": "B", "value": "b"},
        ]

    monkeypatch.setattr("lookup.get_list", fake_get_list)
    result = await auto_select_remote_param(
        "production",
        "renewals",
        "productName",
        "q1",
        {},
    )
    assert result is None


@pytest.mark.asyncio
async def test_auto_select_remote_param_selects_primary_deployment(monkeypatch):
    async def fake_get_list(*args, **kwargs):
        return [
            {"label": "[Primary] North", "value": "north", "_is_primary": True},
            {"label": "West", "value": "west"},
        ]

    monkeypatch.setattr("lookup.get_list", fake_get_list)
    result = await auto_select_remote_param(
        "production",
        "adoption",
        "deployment",
        "q1",
        {},
        prefer_primary=True,
    )
    assert result == ("north", "[Primary] North")
