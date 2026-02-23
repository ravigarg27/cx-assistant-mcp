import json
import re
from pathlib import Path
from rapidfuzz import process, fuzz

_CATALOG: list | None = None


def _load_catalog() -> list:
    global _CATALOG
    if _CATALOG is None:
        path = Path(__file__).parent / "catalog.json"
        raw = json.loads(path.read_text())
        # Handle both flat list and wrapped object formats
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
        scorer=fuzz.WRatio,
        score_cutoff=threshold,
    )
    if result is None:
        return None
    matched_id = result[2]
    return next(q for q in catalog if q["id"] == matched_id)


_KNOWN_PRODUCTS = [
    "DUO", "UMBRELLA", "ISE", "SECURE_FIREWALL", "INTERSIGHT",
    "WIRELESS", "COLLAB", "SD-WAN", "SECURE_CLIENT", "SECURE_EMAIL",
    "SECURE_MALWARE_ANALYTICS", "SECURE_WEB_APPLIANCE", "EPP",
    "VULNERABILITY_MANAGEMENT", "SAN", "NX9K", "NX3K",
]


def extract_parameters(message: str, param_names: list[str]) -> dict:
    """Extract known parameter values from a natural language message."""
    extracted: dict = {}
    for name in param_names:
        extracted[name] = None
        if name == "dealId":
            m = re.search(r"\bD-\d+\b", message, re.IGNORECASE)
            extracted[name] = m.group(0).upper() if m else None
        elif name == "customerName":
            # Prefer explicit CAV BU ID (5-6 digit number)
            m = re.search(r"\b(\d{5,6})\b", message)
            if m:
                extracted[name] = m.group(1)
            else:
                # Fall back to text after "for" or "of"
                m = re.search(r"\b(?:for|of)\s+([A-Z][^\n,?]+)", message)
                extracted[name] = m.group(1).strip() if m else None
        elif name == "productName":
            msg_upper = message.upper()
            for product in _KNOWN_PRODUCTS:
                if product.replace("_", " ") in msg_upper or product in msg_upper:
                    extracted[name] = product
                    break
        elif name == "accountId":
            m = re.search(r"\b([A-Z0-9]{6,})\b", message)
            extracted[name] = m.group(1) if m else None
    return extracted


_PARAM_EXAMPLES = {
    "dealId": "D-12345",
    "customerName": "Acme Corp or CAV BU ID like 104461",
    "productName": "DUO, UMBRELLA, ISE, etc.",
    "accountId": "your Splunk account ID",
    "service": "the service name",
    "deployment": "the deployment name",
    "featureName": "the feature name",
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
    return "\n".join(lines)
