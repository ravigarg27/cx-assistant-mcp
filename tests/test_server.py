import pytest

import server


def test_build_dependent_body_uses_catalog_api_param_mapping():
    question = {
        "parameters": [
            {
                "name": "subBusinessEntities",
                "api": {
                    "params": {
                        "customer_hierarchy": {
                            "fieldName": "customerName",
                            "required": True,
                        },
                        "business_entity": {
                            "fieldName": "businessEntities",
                            "required": True,
                        },
                    }
                },
            }
        ]
    }
    parameters = {
        "customerName": {"label": "Acme", "value": "104461"},
        "businessEntities": {"label": "BE", "value": "SERVICES"},
    }
    body = server._build_dependent_body(question, parameters, "subBusinessEntities")
    assert body == {
        "customer_hierarchy": "104461",
        "business_entity": "SERVICES",
    }


def test_build_dependent_body_includes_constant_and_transform():
    question = {
        "parameters": [
            {
                "name": "subBusinessEntity",
                "api": {
                    "params": {
                        "business_entity": {
                            "fieldName": "businessEntity",
                            "transform": "to-array",
                        },
                        "input_type": {"value": "PRODUCT_AND_SERVICE"},
                    }
                },
            }
        ]
    }
    parameters = {
        "businessEntity": {"label": "BE", "value": "SERVICES"},
    }
    body = server._build_dependent_body(question, parameters, "subBusinessEntity")
    assert body == {
        "business_entity": ["SERVICES"],
        "input_type": "PRODUCT_AND_SERVICE",
    }


@pytest.mark.asyncio
async def test_resolve_params_marks_unresolvable_when_customer_lookup_fails(monkeypatch):
    async def fake_search(*args, **kwargs):
        return []

    monkeypatch.setattr(server, "_search_customers", fake_search)

    question = {
        "backendQuestionId": "q1",
        "agent": "renewals",
        "parameters": [{"name": "customerName", "subtype": "remote"}],
    }
    extracted = {
        "customerName": {
            "label": "Unknown Corp",
            "value": "Unknown Corp",
            "_needs_resolution": True,
        }
    }

    params, unresolvable = await server._resolve_params_with_lookups(
        "production",
        question,
        extracted,
        cookies={},
    )
    assert params == {}
    assert unresolvable == ["customerName"]


@pytest.mark.asyncio
async def test_resolve_params_marks_unresolvable_when_remote_hint_cannot_resolve(monkeypatch):
    async def fake_resolve(*args, **kwargs):
        return None

    monkeypatch.setattr(server, "resolve_remote_param", fake_resolve)

    question = {
        "backendQuestionId": "q1",
        "agent": "adoption",
        "parameters": [{"name": "deployment", "subtype": "remote"}],
    }
    extracted = {
        "deployment": {
            "label": "nonexistent deployment",
            "value": "nonexistent deployment",
            "_needs_resolution": True,
        }
    }

    params, unresolvable = await server._resolve_params_with_lookups(
        "production",
        question,
        extracted,
        cookies={},
    )
    assert params == {}
    assert unresolvable == ["deployment"]
