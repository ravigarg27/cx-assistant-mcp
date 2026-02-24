import pytest
from routing import (
    find_best_question,
    extract_parameters,
    build_routing_error,
    get_followups,
)


# --- find_best_question ---

def test_find_renewal_risk_question():
    result = find_best_question("What is the renewal risk for deal D-12345?")
    assert result is not None
    assert result["agent"] == "renewals"
    assert "deal" in result["label"].lower() or "renewal" in result["label"].lower()


def test_find_sentiment_question():
    result = find_best_question("Analyze customer sentiment for Acme Corp")
    assert result is not None
    assert "sentiment" in result["label"].lower() or "sentiment" in result["id"].lower()


def test_low_confidence_returns_none():
    result = find_best_question("xyzzy gobbledygook nonsense asdfqwer", threshold=80)
    assert result is None


# --- extract_parameters (label/value separation) ---

def _make_param_def(name, subtype="remote"):
    return {"name": name, "subtype": subtype}


def test_extract_deal_id_returns_label_value():
    params = extract_parameters(
        "renewal risk for deal D-12345", [_make_param_def("dealId")]
    )
    assert params["dealId"] is not None
    assert params["dealId"]["label"] == "D-12345"
    assert params["dealId"]["value"] == "D-12345"


def test_extract_deal_id_case_insensitive():
    params = extract_parameters(
        "risk for d-99999", [_make_param_def("dealId")]
    )
    assert params["dealId"]["value"] == "D-99999"


def test_extract_cav_bu_id_as_customer():
    params = extract_parameters(
        "products for United Nations CAV BU 104461",
        [_make_param_def("customerName")],
    )
    assert params["customerName"]["value"] == "104461"
    assert "_needs_resolution" not in params["customerName"]


def test_extract_customer_name_text_needs_resolution():
    params = extract_parameters(
        "show me sentiment for Acme Corp",
        [_make_param_def("customerName")],
    )
    assert params["customerName"] is not None
    assert params["customerName"]["_needs_resolution"] is True
    assert "Acme" in params["customerName"]["label"]


def test_extract_customer_name_lowercase():
    """Bug fix: lowercase names after 'for' were rejected by [A-Z] regex."""
    params = extract_parameters(
        "show sentiment for acme corp",
        [_make_param_def("customerName")],
    )
    assert params["customerName"] is not None
    assert "acme" in params["customerName"]["label"].lower()


def test_missing_customer_returns_none():
    params = extract_parameters(
        "show me sentiment", [_make_param_def("customerName")]
    )
    assert params["customerName"] is None


# --- Product extraction (full 24-product list with labels) ---

def test_extract_product_duo():
    params = extract_parameters(
        "adoption for DUO product", [_make_param_def("productName")]
    )
    assert params["productName"]["value"] == "DUO"
    assert params["productName"]["label"] == "Duo"


def test_extract_product_umbrella():
    params = extract_parameters(
        "customer sentiment towards Umbrella", [_make_param_def("productName")]
    )
    assert params["productName"]["value"] == "UMBRELLA"
    assert params["productName"]["label"] == "Umbrella"


def test_extract_product_defense_orchestrator():
    """Verify a product that was missing from the old list is now found."""
    params = extract_parameters(
        "show Defense Orchestrator metrics", [_make_param_def("productName")]
    )
    assert params["productName"]["value"] == "DEFENSE_ORCHESTRATOR"
    assert params["productName"]["label"] == "Defense Orchestrator"


def test_extract_product_crosswork_cloud():
    params = extract_parameters(
        "risk for Crosswork Cloud", [_make_param_def("productName")]
    )
    assert params["productName"]["value"] == "CROSSWORK_CLOUD"
    assert params["productName"]["label"] == "Crosswork Cloud"


def test_extract_product_enterprise_switching():
    params = extract_parameters(
        "metrics for Enterprise Switching", [_make_param_def("productName")]
    )
    assert params["productName"]["value"] == "ENTERPRISE_SWITCHING"
    assert params["productName"]["label"] == "Enterprise Switching"


def test_extract_product_sdwan_alias():
    params = extract_parameters(
        "show sdwan details", [_make_param_def("productName")]
    )
    assert params["productName"]["value"] == "SD-WAN"


def test_extract_product_firewall_short():
    params = extract_parameters(
        "customer using firewall", [_make_param_def("productName")]
    )
    assert params["productName"]["value"] == "SECURE_FIREWALL"


def test_missing_product_returns_none():
    params = extract_parameters(
        "show me risk details", [_make_param_def("productName")]
    )
    assert params["productName"] is None


# --- Static select extraction ---

def test_extract_service_advanced():
    params = extract_parameters(
        "sentiment towards Advanced Services",
        [{"name": "service", "subtype": "static", "options": [
            {"label": "Advanced Services", "value": "advanced services"},
            {"label": "Technical Services", "value": "technical services"},
        ]}],
    )
    assert params["service"]["value"] == "advanced services"
    assert params["service"]["label"] == "Advanced Services"


def test_extract_timeframe():
    params = extract_parameters(
        "show metrics for last quarter",
        [{"name": "timeframe", "subtype": "static", "options": [
            {"label": "Current quarter", "value": "current quarter"},
            {"label": "Last quarter", "value": "last quarter"},
        ]}],
    )
    assert params["timeframe"]["value"] == "last quarter"


def test_extract_region():
    params = extract_parameters(
        "customers in APJC region",
        [{"name": "region", "subtype": "static", "options": [
            {"label": "Americas", "value": "Americas"},
            {"label": "EMEAR", "value": "EMEAR"},
            {"label": "APJC", "value": "APJC"},
        ]}],
    )
    assert params["region"]["value"] == "APJC"


def test_extract_comparison():
    params = extract_parameters(
        "compare by market segment",
        [{"name": "comparison", "subtype": "static", "options": [
            {"label": "Region", "value": "region"},
            {"label": "Market Segment", "value": "market segment"},
            {"label": "Industry Vertical", "value": "industry vertical"},
        ]}],
    )
    assert params["comparison"]["value"] == "market segment"


def test_extract_forecast_status():
    params = extract_parameters(
        "show commit deals",
        [{"name": "forecastStatuses", "subtype": "static", "options": [
            {"label": "Commit", "value": "Commit"},
            {"label": "Upside", "value": "Upside"},
        ]}],
    )
    assert params["forecastStatuses"]["value"] == "Commit"


def test_extract_tac_sentiment_time_period():
    params = extract_parameters(
        "TAC sentiment for current quarter",
        [{"name": "tacSentimentTimePeriod", "subtype": "static", "options": [
            {"label": "Current quarter", "value": "current quarter"},
            {"label": "Last quarter", "value": "last quarter"},
        ]}],
    )
    assert params["tacSentimentTimePeriod"]["value"] == "current quarter"


# --- Opportunity ID ---

def test_extract_opportunity_id():
    params = extract_parameters(
        "link opportunity 12345678", [_make_param_def("opportunityId")]
    )
    assert params["opportunityId"]["value"] == "12345678"


# --- Account ID ---

def test_extract_account_id():
    params = extract_parameters(
        "Splunk for account ABC123DEF",
        [_make_param_def("accountId")],
    )
    assert params["accountId"]["value"] == "ABC123DEF"


# --- build_routing_error ---

def test_build_routing_error_includes_question_label():
    question = {"label": "Summarize the renewal risk of a deal", "backendQuestionId": "q2"}
    error = build_routing_error(question, ["dealId"])
    assert "Summarize the renewal risk of a deal" in error
    assert "dealId" in error
    assert "D-12345" in error


def test_build_routing_error_shows_product_examples():
    question = {"label": "Show adoption", "backendQuestionId": "q1"}
    error = build_routing_error(question, ["productName"])
    assert "Duo" in error or "Umbrella" in error or "ISE" in error


def test_build_routing_error_shows_timeframe_examples():
    question = {"label": "Show metrics", "backendQuestionId": "q1"}
    error = build_routing_error(question, ["timeframe"])
    assert "quarter" in error.lower()


# --- get_followups ---

def test_get_followups_returns_list():
    q = find_best_question("Analyze customer sentiment for Acme Corp")
    if q is None:
        pytest.skip("Could not find sentiment question in catalog")
    followups = get_followups(q)
    assert isinstance(followups, list)


def test_get_followups_empty_for_no_followups():
    followups = get_followups({"followups": []})
    assert followups == []

    followups = get_followups({})
    assert followups == []
