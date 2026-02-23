import pytest
from routing import find_best_question, extract_parameters, build_routing_error

def test_find_renewal_risk_question():
    result = find_best_question("What is the renewal risk for deal D-12345?")
    assert result is not None
    assert result["agent"] == "renewals"
    # should match a deal-related question
    assert "deal" in result["label"].lower() or "renewal" in result["label"].lower()

def test_find_sentiment_question():
    result = find_best_question("Analyze customer sentiment for Acme Corp")
    assert result is not None
    assert "sentiment" in result["label"].lower() or "sentiment" in result["id"].lower()

def test_low_confidence_returns_none():
    result = find_best_question("xyzzy gobbledygook nonsense asdfqwer", threshold=80)
    assert result is None

def test_extract_deal_id():
    params = extract_parameters("renewal risk for deal D-12345", ["dealId"])
    assert params["dealId"] == "D-12345"

def test_extract_cav_bu_id_as_customer():
    params = extract_parameters("products for United Nations CAV BU 104461", ["customerName"])
    assert params["customerName"] == "104461"

def test_extract_customer_name_fallback():
    params = extract_parameters("show me sentiment for Acme Corp", ["customerName"])
    assert params["customerName"] is not None

def test_extract_product_name_duo():
    params = extract_parameters("show adoption for DUO product", ["productName"])
    assert params["productName"] == "DUO"

def test_extract_product_name_umbrella():
    params = extract_parameters("customer sentiment towards Umbrella", ["productName"])
    assert params["productName"] == "UMBRELLA"

def test_missing_parameter_returns_none():
    params = extract_parameters("renewal risk for a deal", ["dealId"])
    assert params["dealId"] is None

def test_build_routing_error_includes_question_label():
    question = {"label": "Summarize the renewal risk of a deal", "backendQuestionId": "q2"}
    error = build_routing_error(question, ["dealId"])
    assert "Summarize the renewal risk of a deal" in error
    assert "dealId" in error
    assert "D-12345" in error  # example value
