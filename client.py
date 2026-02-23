import json
import uuid
import httpx

HOSTS = {
    "production": "https://cxassistant.cisco.com",
    "stage": "https://cxassistant-stage.cisco.com"
}

def build_structured_body(
    question: str,
    question_id: str,
    frontend_id: str,
    agent: str,
    parameters: dict,
) -> dict:
    """Build request body for POST /api/{agent}/message."""
    return {
        "question": question,
        "questionId": question_id,
        "frontendId": frontend_id,
        "threadId": str(uuid.uuid4()),
        "parameters": parameters,
        "agent": agent,
    }

def parse_sse_response(raw: str) -> str:
    """Parse SSE stream text. Prefer final event; fall back to accumulated tokens."""
    chunks = raw.split("\n\n")
    # Pass 1: look for final event
    for chunk in chunks:
        if not chunk.startswith("data: "):
            continue
        try:
            evt = json.loads(chunk[6:])
            if evt.get("event_type") == "final":
                return evt["data"]["response"]
        except Exception:
            pass
    # Pass 2: accumulate token chunks
    tokens = []
    for chunk in chunks:
        if not chunk.startswith("data: "):
            continue
        try:
            evt = json.loads(chunk[6:])
            if evt.get("event_type") == "token":
                tokens.append(evt["data"]["content"])
        except Exception:
            pass
    return "".join(tokens)

async def call_structured(
    environment: str,
    agent: str,
    body: dict,
    cookies: dict,
    timeout: int = 120,
) -> tuple[int, str]:
    """POST to /api/{agent}/message. Returns (status_code, content_string)."""
    url = f"{HOSTS[environment]}/api/{agent}/message"
    async with httpx.AsyncClient(cookies=cookies, timeout=timeout) as client:
        resp = await client.post(url, json=body)
        if resp.status_code == 200:
            return 200, resp.json().get("content", "")
        return resp.status_code, ""

async def call_open_prompt(
    environment: str,
    message: str,
    cookies: dict,
    timeout: int = 120,
) -> tuple[int, str]:
    """POST to /api/supervisor/stream, parse SSE. Returns (status_code, response_string)."""
    url = f"{HOSTS[environment]}/api/supervisor/stream"
    body = {
        "message": message,
        "thread_id": str(uuid.uuid4()),
        "rbac_access_scope": "my",
    }
    raw = ""
    async with httpx.AsyncClient(cookies=cookies, timeout=timeout) as client:
        async with client.stream(
            "POST", url, json=body, headers={"Accept": "text/event-stream"}
        ) as resp:
            if resp.status_code != 200:
                return resp.status_code, ""
            async for chunk in resp.aiter_text():
                raw += chunk
    return 200, parse_sse_response(raw)
