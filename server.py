from fastmcp import FastMCP
from auth import browser_login, load_cookies, cookies_as_dict
from routing import find_best_question, extract_parameters, build_routing_error
from client import build_structured_body, call_structured, call_open_prompt

mcp = FastMCP("cx-assistant")


async def _ask_structured(environment: str, message: str) -> str:
    """Shared implementation for structured tools."""
    question = find_best_question(message)
    if question is None:
        return (
            "Could not find a matching question in the catalog. "
            f"Try ask_{environment}_open for free-form questions."
        )
    param_names = [p["name"] for p in question.get("parameters", [])]
    extracted = extract_parameters(message, param_names)
    missing = [k for k, v in extracted.items() if v is None]
    if missing:
        return build_routing_error(question, missing)
    parameters = {
        k: {"label": v, "value": v, "hidden": False}
        for k, v in extracted.items()
        if v is not None
    }
    body = build_structured_body(
        question=question["label"],
        question_id=question["backendQuestionId"],
        frontend_id=question["id"],
        agent=question["agent"],
        parameters=parameters,
    )
    cookies_list = load_cookies()
    if not cookies_list:
        return f"Not authenticated. Ask me to 'login to CX Assistant {environment}' first."
    cookies = cookies_as_dict(cookies_list)
    status, result = await call_structured(environment, question["agent"], body, cookies)
    if status == 401:
        await browser_login(environment)
        cookies = cookies_as_dict(load_cookies())
        status, result = await call_structured(environment, question["agent"], body, cookies)
    if status != 200:
        return f"API error: HTTP {status}"
    return result


async def _ask_open(environment: str, message: str) -> str:
    """Shared implementation for open prompt tools."""
    cookies_list = load_cookies()
    if not cookies_list:
        return f"Not authenticated. Ask me to 'login to CX Assistant {environment}' first."
    cookies = cookies_as_dict(cookies_list)
    status, result = await call_open_prompt(environment, message, cookies)
    if status == 404:
        return (
            f"Open prompt endpoint not available on {environment}. "
            f"Try ask_{environment}_structured instead."
        )
    if status == 401:
        await browser_login(environment)
        cookies = cookies_as_dict(load_cookies())
        status, result = await call_open_prompt(environment, message, cookies)
    if status != 200:
        return f"API error: HTTP {status}"
    return result


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


if __name__ == "__main__":
    mcp.run()
