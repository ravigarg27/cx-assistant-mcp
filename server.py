"""CX Assistant MCP Server.

Exposes tools for querying CX Assistant production and stage environments
with automatic question routing, parameter resolution, and follow-up support.
"""

import re

from fastmcp import FastMCP
from auth import browser_login, load_cookies, cookies_as_dict, get_cookies_path
from routing import (
    find_best_question,
    extract_parameters,
    build_routing_error,
    get_followups,
)
from client import build_structured_body, call_structured, call_open_prompt
from lookup import (
    search_customers as _search_customers,
    resolve_remote_param,
    auto_select_remote_param,
    send_feedback as _send_feedback,
)

mcp = FastMCP("cx-assistant")

# Track the last thread ID and request type per environment.
_last_thread: dict[str, str] = {}
_last_source: dict[str, str] = {}  # "structured" or "open"


def _get_cookies_or_error(environment: str) -> dict | str:
    """Load cookies or return an error message string."""
    cookies_list = load_cookies(path=get_cookies_path(environment))
    if not cookies_list:
        return f"Not authenticated. Ask me to 'login to CX Assistant {environment}' first."
    return cookies_as_dict(cookies_list)


async def _refresh_cookies(environment: str) -> dict | str:
    """Re-authenticate and return fresh cookies, or error string."""
    await browser_login(environment)
    refreshed = load_cookies(path=get_cookies_path(environment))
    if not refreshed:
        return "Login failed. Please use the login tool and try again."
    return cookies_as_dict(refreshed)


def _format_followups(question: dict) -> str:
    """Format follow-up question suggestions as a markdown section."""
    followups = get_followups(question)
    if not followups:
        return ""
    lines = ["\n\n---\n**Suggested follow-ups:**"]
    for fu in followups:
        lines.append(f"- {fu['label']}")
    return "\n".join(lines)


_FALLBACK_PARAM_DEPS: dict[str, list[str]] = {
    "deployment": ["customerName", "productName"],
    "deploymentList": ["customerName", "productName"],
    "outcome": ["customerName", "productName", "deploymentList"],
    "outcomes": ["customerName", "productName", "deploymentList"],
    "featureName": ["customerName", "productName"],
    "marketSegment": ["customerName"],
    "vertical": ["customerName"],
    "subBusinessEntity": ["customerName"],
    "subBusinessEntities": ["customerName"],
    "subBusinessServiceCategoryMultiSelect": ["customerName"],
    "metrics": ["customerName", "productName"],
}

_FALLBACK_FIELD_NAME_MAP: dict[str, dict[str, str]] = {
    "outcome": {"deploymentList": "deployment"},
    "outcomes": {"deploymentList": "deployment"},
    "subBusinessEntity": {"customerName": "customer_hierarchy"},
    "subBusinessEntities": {
        "customerName": "customer_hierarchy",
        "businessEntities": "business_entity",
    },
    "subBusinessServiceCategoryMultiSelect": {
        "customerName": "customer_hierarchy",
    },
    "metrics": {"customerName": "customerName", "productName": "productName"},
}


def _get_param_def(question: dict, param_name: str) -> dict | None:
    for pdef in question.get("parameters", []):
        if pdef.get("name") == param_name:
            return pdef
    return None


_VALUE_FIELD_RE = re.compile(r"'value'\s*:\s*\$\.(\w+)")


def _uses_summary_as_value(question: dict, param_name: str) -> bool:
    """Check if the catalog transform maps value to OUTCOME_SUMMARY.

    Some questions (e.g. Q21, Q27) use OUTCOME_SUMMARY as the parameter
    value while others (e.g. Q36) use OUTCOME_ID.
    """
    pdef = _get_param_def(question, param_name)
    if not pdef:
        return False
    transform = (pdef.get("api") or {}).get("transform", "")
    m = _VALUE_FIELD_RE.search(transform)
    return m is not None and m.group(1) == "OUTCOME_SUMMARY"


def _build_dependent_body(question: dict, parameters: dict, param_name: str) -> dict | None:
    """Build the extra_body dict with resolved dependency values for a lookup API.

    Deployment lookups need customerName + productName.
    Outcome lookups need customerName + productName + deployment (as array).
    Uses per-target fieldName mappings from the catalog where param names
    differ from the API body keys.
    """
    param_def = _get_param_def(question, param_name)
    api_params = (param_def or {}).get("api", {}).get("params", {})
    body = {}
    if isinstance(api_params, dict) and api_params:
        for api_key, spec in api_params.items():
            if not isinstance(spec, dict):
                continue
            if "value" in spec:
                body[api_key] = spec["value"]
                continue
            source = spec.get("fieldName")
            if not source:
                continue

            raw_val = None
            if source in parameters:
                raw_val = parameters[source]["value"]
            elif source == "deploymentList" and "deployment" in parameters:
                raw_val = parameters["deployment"]["value"]
            elif source == "deployment" and "deploymentList" in parameters:
                raw_val = parameters["deploymentList"]["value"]

            if raw_val is None:
                continue
            if spec.get("transform") == "to-array" and not isinstance(raw_val, list):
                raw_val = [raw_val]
            elif api_key in ("deploymentList",) and not isinstance(raw_val, list):
                raw_val = [raw_val]
            body[api_key] = raw_val
        if body:
            return body

    needed = _FALLBACK_PARAM_DEPS.get(param_name)
    if not needed:
        return None
    field_map = _FALLBACK_FIELD_NAME_MAP.get(param_name, {})
    for dep in needed:
        raw_val = None
        if dep in parameters:
            raw_val = parameters[dep]["value"]
        elif dep == "deploymentList" and "deployment" in parameters:
            raw_val = parameters["deployment"]["value"]

        if raw_val is None:
            continue

        if dep == "deploymentList":
            raw_val = [raw_val] if not isinstance(raw_val, list) else raw_val

        api_key = field_map.get(dep, dep)
        body[api_key] = raw_val
    return body if body else None


_RESOLVE_ORDER = [
    "customerName", "productName",
    "businessEntity", "businessEntities",
    "subBusinessEntity", "subBusinessEntities",
    "subBusinessServiceCategoryMultiSelect",
    "marketSegment", "vertical",
    "deployment", "deploymentList",
    "outcome", "outcomes",
    "featureName", "metrics",
]


async def _resolve_params_with_lookups(
    environment: str,
    question: dict,
    extracted: dict,
    cookies: dict,
) -> tuple[dict, list[str]]:
    """Resolve extracted parameters that need API lookups.

    Handles customer name resolution, remote-select fuzzy matching, and
    auto-selection for params the user didn't specify. Resolves in
    dependency order so deployment/outcome lookups receive the resolved
    customer and product values.

    Returns (parameters_dict, list_of_unresolvable_param_names).
    """
    parameters: dict = {}
    unresolvable: list[str] = []
    question_id = question["backendQuestionId"]
    agent = question["agent"]

    ordered_names = sorted(
        extracted.keys(),
        key=lambda n: _RESOLVE_ORDER.index(n) if n in _RESOLVE_ORDER else 99,
    )

    for name in ordered_names:
        val = extracted[name]

        if val is None:
            unresolvable.append(name)
            continue

        try:
            auto_resolve = isinstance(val, dict) and val.get("_auto_resolve")
            needs_resolution = isinstance(val, dict) and val.get("_needs_resolution")

            if name == "customerName" and needs_resolution:
                results = await _search_customers(
                    environment, question_id, val["label"], cookies
                )
                if results:
                    val = {"label": results[0]["label"], "value": results[0]["value"]}
                else:
                    unresolvable.append(name)
                    continue

            elif auto_resolve:
                dep_body = _build_dependent_body(question, parameters, name)
                prefer_primary = name in ("deployment", "deploymentList")
                resolved = await auto_select_remote_param(
                    environment, agent, name, question_id, cookies,
                    dependent_params=dep_body,
                    prefer_primary=prefer_primary,
                )
                if resolved:
                    val = {"label": resolved[1], "value": resolved[0]}
                else:
                    unresolvable.append(name)
                    continue

            elif needs_resolution:
                dep_body = _build_dependent_body(question, parameters, name)
                resolved = await resolve_remote_param(
                    environment, agent, name, question_id, val["label"], cookies,
                    dependent_params=dep_body,
                )
                if not resolved and name in ("outcome", "outcomes"):
                    resolved = await auto_select_remote_param(
                        environment, agent, name, question_id, cookies,
                        dependent_params=dep_body,
                    )
                if resolved:
                    val = {"label": resolved[1], "value": resolved[0]}
                else:
                    unresolvable.append(name)
                    continue

            else:
                param_def = next(
                    (p for p in question.get("parameters", []) if p["name"] == name),
                    None,
                )
                if (
                    param_def
                    and param_def.get("subtype") == "remote"
                    and isinstance(val, dict)
                ):
                    dep_body = _build_dependent_body(question, parameters, name)
                    hint = val.get("label") or val.get("value", "")
                    resolved = await resolve_remote_param(
                        environment, agent, name, question_id, hint, cookies,
                        dependent_params=dep_body,
                    )
                    if resolved:
                        val = {"label": resolved[1], "value": resolved[0]}
                    else:
                        unresolvable.append(name)
                        continue

            if name in ("outcome", "outcomes") and _uses_summary_as_value(question, name):
                val = {"label": val["label"], "value": val["label"]}

            param_def = _get_param_def(question, name)
            final_value = val["value"]
            if param_def and param_def.get("multiple") and not isinstance(final_value, list):
                final_value = [final_value]

            clean = {
                "label": val["label"],
                "value": final_value,
                "hidden": val.get("hidden", False),
            }
            parameters[name] = clean

        except Exception:
            unresolvable.append(name)

    return parameters, unresolvable


async def _ask_structured(environment: str, message: str) -> str:
    """Shared implementation for structured tools."""
    question = find_best_question(message)
    if question is None:
        return (
            "Could not find a matching question in the catalog. "
            f"Try ask_{environment}_open for free-form questions."
        )

    param_defs = question.get("parameters", [])
    extracted = extract_parameters(message, param_defs)

    truly_missing = [
        k for k, v in extracted.items()
        if v is None
    ]
    if truly_missing:
        return build_routing_error(question, truly_missing)

    cookies = _get_cookies_or_error(environment)
    if isinstance(cookies, str):
        return cookies

    parameters, unresolvable = await _resolve_params_with_lookups(
        environment, question, extracted, cookies
    )
    if unresolvable:
        return build_routing_error(question, unresolvable)

    body = build_structured_body(
        question=question["label"],
        question_id=question["backendQuestionId"],
        frontend_id=question["id"],
        agent=question["agent"],
        parameters=parameters,
        thread_id=_last_thread.get(environment),
    )

    status, result = await call_structured(environment, question["agent"], body, cookies)
    if status == 401:
        cookies = await _refresh_cookies(environment)
        if isinstance(cookies, str):
            return cookies
        status, result = await call_structured(
            environment, question["agent"], body, cookies
        )
    if status != 200:
        return f"API error: HTTP {status}"

    _last_thread[environment] = body["threadId"]
    _last_source[environment] = "structured"
    return result + _format_followups(question)


async def _ask_open(environment: str, message: str) -> str:
    """Shared implementation for open prompt tools."""
    cookies = _get_cookies_or_error(environment)
    if isinstance(cookies, str):
        return cookies

    status, result, tid = await call_open_prompt(
        environment, message, cookies,
        thread_id=_last_thread.get(environment),
    )

    if status == 404:
        return (
            f"Open prompt endpoint not available on {environment}. "
            f"Try ask_{environment}_structured instead."
        )
    if status == 401:
        cookies = await _refresh_cookies(environment)
        if isinstance(cookies, str):
            return cookies
        status, result, tid = await call_open_prompt(
            environment, message, cookies, thread_id=tid,
        )
    if status != 200:
        return f"API error: HTTP {status}"

    _last_thread[environment] = tid
    _last_source[environment] = "open"
    return result


# --- MCP Tools ---


@mcp.tool()
async def login(environment: str = "production") -> str:
    """Login to CX Assistant via Cisco Duo browser authentication.

    Opens a browser window for you to complete Cisco Duo login.
    Saves your session cookies for subsequent API calls.

    Args:
        environment: 'production' or 'stage' (default: 'production')
    """
    return await browser_login(environment)


@mcp.tool()
async def ask_production_structured(message: str) -> str:
    """Ask a question using CX Assistant production (116 pre-built questions).

    Automatically routes your natural language to the best matching
    pre-built question and extracts required parameters.

    Examples:
        "What is the renewal risk for deal D-12345?"
        "Analyze customer sentiment for Acme Corp"
        "Show adoption level for United Nations CAV BU 104461"

    Args:
        message: Your question in natural language
    """
    return await _ask_structured("production", message)


@mcp.tool()
async def ask_production_open(message: str) -> str:
    """Ask a free-form question using CX Assistant production open prompt.

    Sends your question directly to the production supervisor endpoint.
    Use when the pre-built questions don't cover your use case.

    Args:
        message: Your free-form question
    """
    return await _ask_open("production", message)


@mcp.tool()
async def ask_stage_structured(message: str) -> str:
    """Ask a question using CX Assistant stage environment (pre-built questions).

    Same routing as ask_production_structured but targets stage data.

    Args:
        message: Your question in natural language
    """
    return await _ask_structured("stage", message)


@mcp.tool()
async def ask_stage_open(message: str) -> str:
    """Ask a free-form question using CX Assistant stage open prompt.

    Best for ad-hoc, exploratory questions not covered by the 116-question catalog.

    Examples:
        "What are the adoption barriers for United Nations CAV BU 104461?"
        "Summarize all high-risk contracts expiring in 6 months"

    Args:
        message: Your free-form question
    """
    return await _ask_open("stage", message)


@mcp.tool()
async def search_customers(
    search_text: str, environment: str = "production"
) -> str:
    """Search for customers by name, CAV BU ID, or SAV ID.

    Returns matching customers with their display labels and API values.
    Use this to find the correct customer identifier before asking questions.

    Args:
        search_text: Customer name, CAV BU ID, or SAV ID to search for
        environment: 'production' or 'stage' (default: 'production')
    """
    cookies = _get_cookies_or_error(environment)
    if isinstance(cookies, str):
        return cookies
    results = await _search_customers(environment, "sentimentQ2", search_text, cookies)
    if not results:
        return f"No customers found matching '{search_text}'."
    lines = [f"Found {len(results)} customer(s):"]
    for r in results[:10]:
        lines.append(f"  - {r['label']} (value: {r['value']})")
    if len(results) > 10:
        lines.append(f"  ... and {len(results) - 10} more")
    return "\n".join(lines)


@mcp.tool()
async def give_feedback(
    rating: str,
    environment: str = "production",
    comment: str = "",
    source: str = "",
) -> str:
    """Submit feedback (thumbs up or down) on the last CX Assistant response.

    Args:
        rating: 'up' for positive feedback or 'down' for negative
        environment: 'production' or 'stage' (default: 'production')
        comment: Optional comment explaining the feedback
        source: 'structured' or 'open' (auto-detected from last request if omitted)
    """
    tid = _last_thread.get(environment)
    if not tid:
        return "No recent conversation to provide feedback on."
    cookies = _get_cookies_or_error(environment)
    if isinstance(cookies, str):
        return cookies
    effective_source = source or _last_source.get(environment, "structured")
    endpoint = (
        "/api/supervisor/feedback" if effective_source == "open"
        else "/api/renewals/feedback"
    )
    status, text = await _send_feedback(
        environment, endpoint, tid, rating, cookies, comment=comment
    )
    if status == 401:
        cookies = await _refresh_cookies(environment)
        if isinstance(cookies, str):
            return cookies
        status, text = await _send_feedback(
            environment, endpoint, tid, rating, cookies, comment=comment
        )
    if status == 200:
        return f"Feedback ({rating}) submitted successfully."
    return f"Failed to submit feedback: HTTP {status}"


if __name__ == "__main__":
    mcp.run()
