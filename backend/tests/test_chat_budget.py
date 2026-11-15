"""v1.3.16: the streaming chat endpoint gives the model more time than the plain one.

A hard question on a reasoning model ran past the 50 s budget on production and the
finished data lookups were thrown away with "taking longer than usual". The stream path
keeps the connection alive with heartbeats, so it may wait longer.
"""
import json
from types import SimpleNamespace

import pytest

from app.api.v1 import chat as chat_api


def _events(chunks):
    out = []
    for raw in chunks:
        text = raw.decode() if isinstance(raw, bytes) else raw
        for line in text.splitlines():
            if line.startswith("data:"):
                out.append(json.loads(line[5:].strip()))
    return out


@pytest.mark.asyncio
async def test_stream_runs_the_pipeline_with_the_stream_budget(monkeypatch):
    seen = {}

    async def fake_chat(req, user, db):
        seen["budget"] = chat_api._BUDGET.get()
        return chat_api.ChatResponse(answer="Hello there.", sources=[], session_id="s1", followups=["More?"])

    monkeypatch.setattr(chat_api, "chat", fake_chat)
    req = chat_api.ChatRequest(message="hi")
    resp = await chat_api.chat_stream(req, user=SimpleNamespace(id="u"), db=None)
    events = _events([c async for c in resp.body_iterator])

    assert seen["budget"] == chat_api.STREAM_BUDGET_S == 150.0
    assert events[0] == {"type": "status", "state": "thinking"}
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Hello there."
    assert events[-1]["type"] == "done" and events[-1]["followups"] == ["More?"]


def test_plain_requests_keep_the_gateway_safe_budget():
    assert chat_api._BUDGET.get() == chat_api.REQUEST_BUDGET_S == 50.0
    assert chat_api.STREAM_BUDGET_S > chat_api.REQUEST_BUDGET_S
