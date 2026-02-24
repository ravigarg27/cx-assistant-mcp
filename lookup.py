"""Parameter resolution APIs for CX Assistant.

Calls the backend lookup endpoints to resolve user-friendly names
into the exact {label, value} pairs the API expects.
"""

import httpx
from typing import Optional

HOSTS = {
    "production": "https://cxassistant.cisco.com",
    "stage": "https://cxassistant-stage.cisco.com",
}

# Complete product list from the CX Assistant catalog (24 products).
# Maps API value -> human-readable label.
PRODUCTS = {
    "COLLAB": "Collaboration",
    "CROSSWORK_CLOUD": "Crosswork Cloud",
    "CROSSWORK_NETWORK_CONTROLLER": "Crosswork Network Controller",
    "DEFENSE_ORCHESTRATOR": "Defense Orchestrator",
    "DUO": "Duo",
    "ENTERPRISE_SWITCHING": "Enterprise Switching",
    "EPP": "Endpoint Protection Platform (EPP)",
    "EVOLVED_PROGRAMMABLE_NETWORK_MANAGER": "Evolved Programmable Network Manager",
    "INTERSIGHT": "Intersight",
    "IOS_XR_FLEXIBLE_CONSUMPTION_MODEL": "IOS XR Flexible Consumption Model",
    "ISE": "Identity Services Engine (ISE)",
    "NETWORK_SERVICE_ORCHESTRATOR": "Network Service Orchestrator",
    "NX3K": "Nexus 3k",
    "NX9K": "Nexus 9k",
    "SAN": "Storage Area Network (SAN)",
    "SD-WAN": "Software-Defined Wide Area Network (SDWAN)",
    "SECURE_CLIENT": "Secure Client",
    "SECURE_EMAIL": "Secure Email",
    "SECURE_FIREWALL": "Secure Firewall",
    "SECURE_MALWARE_ANALYTICS": "Secure Malware Analytics",
    "SECURE_WEB_APPLIANCE": "Secure Web Appliance",
    "UMBRELLA": "Umbrella",
    "VULNERABILITY_MANAGEMENT": "Vulnerability Management",
    "WIRELESS": "Wireless",
}

# Reverse lookup: lowercase label -> (value, label)
_PRODUCT_BY_LABEL = {
    label.lower(): (value, label) for value, label in PRODUCTS.items()
}
# Also allow matching by API key with underscores replaced by spaces
_PRODUCT_BY_KEY = {
    value.replace("_", " ").lower(): (value, label)
    for value, label in PRODUCTS.items()
}
# And exact key match
_PRODUCT_BY_EXACT = {
    value.lower(): (value, label) for value, label in PRODUCTS.items()
}


def resolve_product(text: str) -> Optional[tuple[str, str]]:
    """Match user text against known products.

    Returns (value, label) or None. Tries exact key, label, then
    substring matching against both labels and keys.
    """
    t = text.strip().lower()
    if t in _PRODUCT_BY_EXACT:
        return _PRODUCT_BY_EXACT[t]
    if t in _PRODUCT_BY_LABEL:
        return _PRODUCT_BY_LABEL[t]
    if t in _PRODUCT_BY_KEY:
        return _PRODUCT_BY_KEY[t]
    for key, pair in _PRODUCT_BY_LABEL.items():
        if t in key or key in t:
            return pair
    for key, pair in _PRODUCT_BY_KEY.items():
        if t in key or key in t:
            return pair
    return None


# Static select options extracted from the catalog.
STATIC_OPTIONS: dict[str, list[dict[str, str]]] = {
    "service": [
        {"label": "Advanced Services", "value": "advanced services"},
        {"label": "Technical Services", "value": "technical services"},
    ],
    "tacSentimentTimePeriod": [
        {"label": "Current quarter", "value": "current quarter"},
        {"label": "Last quarter", "value": "last quarter"},
        {"label": "Previous 2 quarters", "value": "last 2 quarters"},
    ],
    "timeframe": [
        {"label": "Current quarter", "value": "current quarter"},
        {"label": "Last quarter", "value": "last quarter"},
        {"label": "Last 3 quarters", "value": "last 3 quarters"},
        {"label": "1 year", "value": "1 year"},
    ],
    "subscriptionTimeframe": [
        {"label": "0-90 days", "value": "0-90 days"},
        {"label": "91-180 days", "value": "91-180 days"},
        {"label": "181-360 days", "value": "181-360 days"},
    ],
    "comparison": [
        {"label": "Region", "value": "region"},
        {"label": "Market Segment", "value": "market segment"},
        {"label": "Industry Vertical", "value": "industry vertical"},
    ],
    "region": [
        {"label": "Americas", "value": "Americas"},
        {"label": "EMEAR", "value": "EMEAR"},
        {"label": "APJC", "value": "APJC"},
    ],
    "forecastStatuses": [
        {"label": "Commit", "value": "Commit"},
        {"label": "Upside", "value": "Upside"},
        {"label": "Most Likely", "value": "Most Likely"},
    ],
    "metricType": [
        {"label": "Feature adoption metrics", "value": "AdoptionMetrics"},
        {"label": "Usage/scale metrics", "value": "UsageMetrics"},
    ],
}


def resolve_static(param_name: str, text: str) -> Optional[tuple[str, str]]:
    """Match user text against static select options.

    Returns (value, label) or None.
    """
    options = STATIC_OPTIONS.get(param_name)
    if not options:
        return None
    t = text.strip().lower()
    for opt in options:
        label = (opt.get("label") or "").lower()
        value = (opt.get("value") or "").lower()
        if t == value or t == label:
            return (opt["value"], opt["label"])
    for opt in options:
        label = (opt.get("label") or "").lower()
        value = (opt.get("value") or "").lower()
        if t in label or label in t:
            return (opt["value"], opt["label"])
        if t in value or value in t:
            return (opt["value"], opt["label"])
    return None


# --- Remote Lookup APIs ---
# These call the CX Assistant backend to resolve parameter values.

async def search_customers(
    environment: str,
    question_id: str,
    search_input: str,
    cookies: dict,
    timeout: int = 30,
) -> list[dict]:
    """Search customers by name, CAV BU ID, or SAV ID.

    Returns list of {"label": "...", "value": "..."} dicts.
    """
    host = HOSTS.get(environment, HOSTS["production"])
    url = f"{host}/api/renewals/customer_search"
    body = {"q_num": question_id, "search_input": search_input}
    async with httpx.AsyncClient(cookies=cookies, timeout=timeout) as client:
        resp = await client.post(url, json=body)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = data.get("results", [])
        if isinstance(results, list):
            return [
                {"label": r.get("label", str(r)), "value": r.get("value", str(r))}
                if isinstance(r, dict)
                else {"label": str(r), "value": str(r)}
                for r in results
            ]
        return []


async def get_list(
    environment: str,
    endpoint: str,
    question_id: str,
    cookies: dict,
    method: str = "POST",
    extra_body: Optional[dict] = None,
    timeout: int = 60,
) -> list[dict]:
    """Generic list fetcher for remote select parameter APIs.

    Returns list of {"label": "...", "value": "..."} dicts.
    Handles the deployment list API's nested deploymentList format.
    """
    host = HOSTS.get(environment, HOSTS["production"])
    url = f"{host}{endpoint}"
    try:
        async with httpx.AsyncClient(cookies=cookies, timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url)
            else:
                body = {"q_num": question_id}
                if extra_body:
                    body.update(extra_body)
                resp = await client.post(url, json=body)
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []

    if "deploymentList" in data:
        return _parse_deployment_list(data["deploymentList"])

    results = data.get("results", data.get("data", []))

    if isinstance(results, dict):
        attrs = results.get("attributes", {})
        for key in ("customer_market_segment", "customer_industry_vertical"):
            if key in attrs and isinstance(attrs[key], list):
                return [{"label": str(v), "value": str(v)} for v in attrs[key]]

    if isinstance(results, list):
        return [_normalize_list_item(r) for r in results]
    return []


def _normalize_list_item(r) -> dict:
    """Convert a raw API list item into a standard {label, value} dict.

    Handles plain strings, standard label/value objects, and outcome
    objects with OUTCOME_SUMMARY / OUTCOME_ID fields.
    """
    if not isinstance(r, dict):
        return {"label": str(r), "value": str(r)}
    label = (
        r.get("label")
        or r.get("OUTCOME_SUMMARY")
        or r.get("name")
        or str(r)
    )
    value = (
        r.get("value")
        or r.get("OUTCOME_ID")
        or r.get("OUTCOME_SUMMARY")
        or r.get("name")
        or str(r)
    )
    return {"label": label, "value": value}


def _parse_deployment_list(deployment_list: list) -> list[dict]:
    """Parse the deployment list API response into label/value pairs.

    The API returns objects with deploymentName, partyName, city, and
    isPrimaryFlag. Primary deployments are labeled accordingly.
    """
    items = []
    for dep in deployment_list:
        if not isinstance(dep, dict):
            continue
        name = dep.get("deploymentName", "")
        party = dep.get("partyName", "")
        city = dep.get("city", "")
        is_primary = dep.get("isPrimaryFlag", False)
        if isinstance(is_primary, str):
            is_primary = is_primary.lower() in ("true", "1", "yes")
        label = f"{name} | {party} | {city}"
        if is_primary:
            label = f"[Primary] {label}"
        items.append({
            "label": label,
            "value": name,
            "_is_primary": is_primary,
        })
    return items


# Convenience wrappers for the most common lookup APIs.

LOOKUP_ENDPOINTS: dict[str, tuple[str, str]] = {
    "productName": ("/api/renewals/get_product_name_list", "POST"),
    "businessEntity": ("/api/renewals/get_business_entity_list", "POST"),
    "businessEntities": ("/api/renewals/get_business_entity_list", "POST"),
    "subBusinessEntity": ("/api/renewals/get_sub_business_entity_list", "POST"),
    "subBusinessEntities": ("/api/renewals/get_sub_business_entity_list", "POST"),
    "subBusinessServiceCategoryMultiSelect": (
        "/api/renewals/get_sub_business_entity_list", "POST"
    ),
    "metricName": ("/api/renewals/get_metric_name_list", "POST"),
    "metrics": ("/api/renewals/get_metric_name_list", "POST"),
    "marketSegment": ("/api/renewals/get_customer_attributes", "POST"),
    "vertical": ("/api/renewals/get_customer_attributes", "POST"),
    "pmg": ("/api/renewals/get_product_mapping_group_list", "POST"),
    "fiscalQuarter": ("/api/renewals/get_fy_qtr_list", "POST"),
    "fiscalQuarters": ("/api/renewals/get_fy_qtr_list", "POST"),
    "riskFactor": ("/api/renewals/get_risk_factor_list", "GET"),
    "stages": ("/api/renewals/get_stage_name_list", "GET"),
    "consumptionValue": ("/api/renewals/get_ea_consumption_suite_value_range", "GET"),
    "renewalProgramLead": ("/api/renewals/get_renewal_program_lead_list", "GET"),
    "summaryCategory": ("/api/renewals/summary_category", "GET"),
    "serviceOffer": ("/api/renewals/get_business_entity_list", "POST"),
    "legacyServiceOffer": ("/api/renewals/get_business_entity_list", "POST"),
}

ADOPTION_LOOKUP_ENDPOINTS: dict[str, tuple[str, str]] = {
    "productName": ("/api/adoption/getProductNameList", "POST"),
    "deployment": ("/api/adoption/getDeploymentList/v3", "POST"),
    "deploymentList": ("/api/adoption/getDeploymentList/v3", "POST"),
    "featureName": ("/api/adoption/getFeatureNameList", "POST"),
    "outcome": ("/api/adoption/getOutcomeList/v3", "POST"),
    "outcomes": ("/api/adoption/getOutcomeList/v3", "POST"),
}


async def resolve_remote_param(
    environment: str,
    agent: str,
    param_name: str,
    question_id: str,
    user_text: str,
    cookies: dict,
    dependent_params: Optional[dict] = None,
) -> Optional[tuple[str, str]]:
    """Resolve a remote-select parameter by fetching options from the API
    and fuzzy-matching the user's input.

    Args:
        dependent_params: Dict of resolved param values to pass as extra body
            fields to the lookup API (e.g. customerName, productName for
            deployment lookups).

    Returns (value, label) or None.
    """
    endpoints = ADOPTION_LOOKUP_ENDPOINTS if agent == "adoption" else LOOKUP_ENDPOINTS
    if param_name not in endpoints:
        return None

    endpoint, method = endpoints[param_name]
    options = await get_list(
        environment, endpoint, question_id, cookies,
        method=method, extra_body=dependent_params,
    )
    if not options:
        return None

    t = user_text.strip().lower()

    if "primary" in t and param_name in ("deployment", "deploymentList"):
        for opt in options:
            if opt.get("_is_primary"):
                return (opt["value"], opt["label"])

    for opt in options:
        label = (opt.get("label") or "").lower()
        value = (opt.get("value") or "").lower()
        if t == value or t == label:
            return (opt["value"], opt["label"])
    for opt in options:
        label = (opt.get("label") or "").lower()
        value = (opt.get("value") or "").lower()
        if t in label or label in t:
            return (opt["value"], opt["label"])
        if t in value or value in t:
            return (opt["value"], opt["label"])
    return None


async def auto_select_remote_param(
    environment: str,
    agent: str,
    param_name: str,
    question_id: str,
    cookies: dict,
    dependent_params: Optional[dict] = None,
    prefer_primary: bool = False,
) -> Optional[tuple[str, str]]:
    """Fetch all options for a remote-select param and auto-select one.

    For deployments, selects the primary deployment if prefer_primary is True
    and a primary exists. Otherwise returns the first option.

    Returns (value, label) or None if no options available.
    """
    endpoints = ADOPTION_LOOKUP_ENDPOINTS if agent == "adoption" else LOOKUP_ENDPOINTS
    if param_name not in endpoints:
        return None

    endpoint, method = endpoints[param_name]
    options = await get_list(
        environment, endpoint, question_id, cookies,
        method=method, extra_body=dependent_params,
    )
    if not options:
        return None

    if prefer_primary and param_name in ("deployment", "deploymentList"):
        for opt in options:
            if opt.get("_is_primary"):
                return (opt["value"], opt["label"])
        for opt in options:
            label = (opt.get("label") or "").lower()
            if "primary" in label:
                return (opt["value"], opt["label"])

    return (options[0]["value"], options[0]["label"])


async def send_feedback(
    environment: str,
    endpoint: str,
    thread_id: str,
    rating: str,
    cookies: dict,
    comment: str = "",
    timeout: int = 30,
) -> tuple[int, str]:
    """Submit feedback (thumbs up/down) for a response.

    Args:
        endpoint: '/api/renewals/feedback' or '/api/supervisor/feedback'
        rating: 'up' or 'down'
    """
    host = HOSTS.get(environment, HOSTS["production"])
    url = f"{host}{endpoint}"
    body = {
        "thread_id": thread_id,
        "rating": rating,
    }
    if comment:
        body["comment"] = comment
    async with httpx.AsyncClient(cookies=cookies, timeout=timeout) as client:
        resp = await client.post(url, json=body)
        return resp.status_code, resp.text
