"""Question routing and parameter extraction for CX Assistant MCP.

Matches natural language to the 116-question catalog via fuzzy search,
extracts parameters with proper label/value separation, and provides
follow-up question support.
"""

import json
import re
from pathlib import Path
from rapidfuzz import process, fuzz
from lookup import (
    PRODUCTS, resolve_product, resolve_static, STATIC_OPTIONS,
    ADOPTION_LOOKUP_ENDPOINTS, LOOKUP_ENDPOINTS,
)

_CATALOG: list | None = None


def _load_catalog() -> list:
    global _CATALOG
    if _CATALOG is None:
        path = Path(__file__).parent / "catalog.json"
        raw = json.loads(path.read_text())
        _CATALOG = raw if isinstance(raw, list) else raw.get("questions", raw.get("data", []))
    return _CATALOG


def find_best_question(message: str, threshold: int = 50) -> dict | None:
    """Fuzzy-match message against catalog labels and templates.
    Returns best matching question dict, or None if score below threshold.
    """
    catalog = _load_catalog()
    choices = {
        q["id"]: f"{q['label']} {q.get('questionTemplate', '')}"
        for q in catalog
    }
    result = process.extractOne(
        message,
        choices,
        scorer=fuzz.token_set_ratio,
        score_cutoff=threshold,
    )
    if result is None:
        return None
    matched_id = result[2]
    return next(q for q in catalog if q["id"] == matched_id)


def get_followups(question: dict) -> list[dict]:
    """Return follow-up question dicts for a matched question.

    Each entry has 'id' and 'label' for display.
    """
    catalog = _load_catalog()
    followup_ids = question.get("followups", [])
    if not followup_ids:
        return []
    catalog_by_id = {q["id"]: q for q in catalog}
    followups = []
    for fid in followup_ids:
        fq = catalog_by_id.get(fid)
        if fq:
            label = fq.get("followupLabel") or fq.get("label", "")
            followups.append({"id": fid, "label": label})
    return followups


# --- Parameter Extraction ---

def extract_parameters(message: str, param_defs: list[dict]) -> dict:
    """Extract parameter values from natural language.

    Args:
        message: User's natural language input.
        param_defs: List of parameter definition dicts from the catalog question.
                    Each has at minimum 'name', optionally 'subtype', 'options'.

    Returns:
        Dict of param_name -> {"label": str, "value": str} or None for each param.
        None means the parameter could not be extracted and needs resolution.
    """
    extracted: dict = {}
    param_names = [p["name"] for p in param_defs]

    for pdef in param_defs:
        name = pdef["name"]
        subtype = pdef.get("subtype", "")
        extracted[name] = None

        if name == "dealId":
            m = re.search(r"\bD-\d+\b", message, re.IGNORECASE)
            if m:
                val = m.group(0).upper()
                extracted[name] = {"label": val, "value": val}

        elif name == "opportunityId":
            m = re.search(r"\b\d{8,}\b", message)
            if m:
                val = m.group(0)
                extracted[name] = {"label": val, "value": val}

        elif name == "accountId":
            m = re.search(r"\b([A-Z0-9]{6,})\b", message)
            if m:
                val = m.group(1)
                extracted[name] = {"label": val, "value": val}

        elif name == "customerName":
            extracted[name] = _extract_customer(message)

        elif name == "productName":
            extracted[name] = _extract_product(message)

        elif name in STATIC_OPTIONS:
            extracted[name] = _extract_static(name, message, pdef)

        elif name == "service":
            extracted[name] = _extract_static("service", message, pdef)

        elif subtype == "remote" and name not in ("customerName", "productName"):
            hint = _extract_remote_hint(name, message)
            if hint:
                extracted[name] = {
                    "label": hint, "value": hint, "_needs_resolution": True,
                }
            else:
                extracted[name] = {"_auto_resolve": True}

    return extracted


def _extract_customer(message: str) -> dict | None:
    """Extract customer identifier from message.

    Prefers numeric CAV BU IDs. Falls back to text after 'for'/'of'.
    Returns {"label": raw_text, "value": raw_text, "_needs_resolution": True}
    for text-based names that should be resolved via customer_search.
    """
    m = re.search(r"\b(\d{5,6})\b", message)
    if m:
        cav_id = m.group(1)
        return {"label": cav_id, "value": cav_id, "_needs_resolution": True}

    m = re.search(r"\b(?:for|of)\s+([A-Za-z][^\n,?]+)", message)
    if m:
        name = m.group(1).strip()
        # Strip trailing parameter-like words
        name = re.sub(r"\s+(CAV BU|product|deal|service)\s*$", "", name, flags=re.IGNORECASE).strip()
        return {"label": name, "value": name, "_needs_resolution": True}

    return None


def _extract_product(message: str) -> dict | None:
    """Extract product name from message using the full 24-product list.

    Tries exact API key match, then label match, then substring matching.
    """
    msg_upper = message.upper()
    msg_lower = message.lower()

    # Try matching by API key (with underscores as spaces)
    for api_value, label in PRODUCTS.items():
        key_spaced = api_value.replace("_", " ")
        if key_spaced in msg_upper or api_value in msg_upper:
            return {"label": label, "value": api_value}

    # Try matching by label (case-insensitive)
    for api_value, label in PRODUCTS.items():
        if label.lower() in msg_lower:
            return {"label": label, "value": api_value}

    # Try partial matches for common short names
    _SHORT_NAMES = {
        "duo": "DUO",
        "umbrella": "UMBRELLA",
        "ise": "ISE",
        "intersight": "INTERSIGHT",
        "wireless": "WIRELESS",
        "collab": "COLLAB",
        "sd-wan": "SD-WAN",
        "sdwan": "SD-WAN",
        "firewall": "SECURE_FIREWALL",
        "epp": "EPP",
        "nexus 9k": "NX9K",
        "nexus 3k": "NX3K",
        "san": "SAN",
    }
    for short, api_value in _SHORT_NAMES.items():
        if re.search(r"\b" + re.escape(short) + r"\b", msg_lower):
            return {"label": PRODUCTS[api_value], "value": api_value}

    return None


def _extract_static(param_name: str, message: str, pdef: dict) -> dict | None:
    """Extract a static-select parameter by matching against known options.

    First tries the catalog-embedded options, then the STATIC_OPTIONS table.
    """
    # Use options from the catalog parameter definition if available
    options = pdef.get("options", [])
    if options:
        msg_lower = message.lower()
        for opt in options:
            if opt["value"].lower() in msg_lower or opt["label"].lower() in msg_lower:
                return {"label": opt["label"], "value": opt["value"]}

    result = resolve_static(param_name, message)
    if result:
        return {"label": result[1], "value": result[0]}

    return None


_DEPLOYMENT_PATTERNS = [
    re.compile(r"\bprimary\s+deployment\b", re.IGNORECASE),
    re.compile(r"\bdeployment\s+(\S+)", re.IGNORECASE),
]

_OUTCOME_KEYWORDS = [
    "secure access", "secure network", "secure endpoint",
    "network automation", "network visibility", "collaboration",
    "data center", "cloud security", "threat defense",
]


def _extract_remote_hint(param_name: str, message: str) -> str | None:
    """Try to extract a text hint for a remote-select parameter.

    Returns raw text to fuzzy-match against API options, or None to
    trigger auto-selection.
    """
    msg_lower = message.lower()

    if param_name in ("deployment", "deploymentList"):
        if "primary" in msg_lower:
            return "primary"
        for pat in _DEPLOYMENT_PATTERNS:
            m = pat.search(message)
            if m and m.lastindex:
                return m.group(1).strip()
        return None

    if param_name in ("outcome", "outcomes"):
        for kw in _OUTCOME_KEYWORDS:
            if kw in msg_lower:
                return kw
        return None

    if param_name == "featureName":
        m = re.search(r"\bfeature\s+([A-Za-z][^\n,?]*)", message, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    return None


_PARAM_EXAMPLES = {
    "dealId": "D-12345",
    "customerName": "Acme Corp or CAV BU ID like 104461",
    "productName": "Duo, Umbrella, ISE, Secure Firewall, etc.",
    "accountId": "your Splunk account ID",
    "service": "Advanced Services or Technical Services",
    "deployment": "the deployment name",
    "featureName": "the feature name",
    "outcome": "the adoption outcome",
    "outcomes": "one or more adoption outcomes",
    "timeframe": "current quarter, last quarter, last 3 quarters, or 1 year",
    "tacSentimentTimePeriod": "current quarter, last quarter, or previous 2 quarters",
    "subscriptionTimeframe": "0-90 days, 91-180 days, or 181-360 days",
    "region": "Americas, EMEAR, or APJC",
    "comparison": "region, market segment, or industry vertical",
    "forecastStatuses": "Commit, Upside, or Most Likely",
    "metricType": "feature adoption metrics or usage/scale metrics",
    "opportunityId": "the opportunity ID number",
    "fiscalQuarter": "a fiscal quarter",
    "fiscalQuarters": "one or more fiscal quarters",
    "businessEntity": "a business entity",
    "stages": "one or more deal stages",
    "riskFactor": "a risk factor name",
    "renewalProgramLead": "a renewal program lead",
    "consumptionValue": "an EA consumption value range",
    "pmg": "a product mapping group",
    "vertical": "an industry vertical",
    "marketSegment": "a market segment",
    "deploymentList": "a deployment for the plan",
}


def build_routing_error(question: dict, missing_params: list[str]) -> str:
    """Return a helpful error message listing what parameters are needed."""
    lines = [
        f"Found question: '{question['label']}'",
        "Missing required parameters:",
    ]
    for param in missing_params:
        example = _PARAM_EXAMPLES.get(param, "a valid value")
        lines.append(f"  - {param}: e.g. {example}")
    lines.append("")
    lines.append("Please include these values in your question and try again.")
    return "\n".join(lines)
