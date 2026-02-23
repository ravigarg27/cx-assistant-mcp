import pytest
from client import build_structured_body, parse_sse_response

def test_build_structured_body_has_required_fields():
    body = build_structured_body(
        question="Summarize the renewal risk of a deal",
        question_id="q2",
        frontend_id="renewals:question:2",
        agent="renewals",
        parameters={"dealId": {"label": "D-12345", "value": "D-12345", "hidden": False}}
    )
    assert body["questionId"] == "q2"
    assert body["frontendId"] == "renewals:question:2"
    assert body["agent"] == "renewals"
    assert body["question"] == "Summarize the renewal risk of a deal"
    assert "threadId" in body
    assert body["parameters"]["dealId"]["value"] == "D-12345"

def test_build_structured_body_generates_unique_thread_ids():
    body1 = build_structured_body("q", "q1", "a:q:1", "renewals", {})
    body2 = build_structured_body("q", "q1", "a:q:1", "renewals", {})
    assert body1["threadId"] != body2["threadId"]

def test_parse_sse_prefers_final_event():
    raw = (
        'data: {"event_type": "worklog", "data": {"message": "working..."}}\n\n'
        'data: {"event_type": "token", "data": {"content": "partial"}}\n\n'
        'data: {"event_type": "final", "data": {"response": "complete answer"}}\n\n'
    )
    assert parse_sse_response(raw) == "complete answer"

def test_parse_sse_fallback_to_tokens_when_no_final():
    raw = (
        'data: {"event_type": "token", "data": {"content": "hello "}}\n\n'
        'data: {"event_type": "token", "data": {"content": "world"}}\n\n'
    )
    assert parse_sse_response(raw) == "hello world"

def test_parse_sse_empty_input_returns_empty():
    assert parse_sse_response("") == ""

def test_parse_sse_ignores_malformed_lines():
    raw = (
        'data: not valid json\n\n'
        'data: {"event_type": "final", "data": {"response": "ok"}}\n\n'
    )
    assert parse_sse_response(raw) == "ok"

def test_parse_sse_ignores_worklog_events():
    raw = (
        'data: {"event_type": "worklog", "data": {"message": "stage 1"}}\n\n'
        'data: {"event_type": "worklog", "data": {"message": "stage 2"}}\n\n'
    )
    assert parse_sse_response(raw) == ""
