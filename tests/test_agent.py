"""Tests for the agent loop. Claude is replaced by a fake client that returns
scripted responses, so no API calls are made."""

import json
from types import SimpleNamespace

import pytest

from app import agent, tools

FINAL = {
    "answer": "Minneapolis is most exposed.",
    "ranking": [{"hub_id": "minneapolis", "hub_name": "Minneapolis Hub",
                 "score": 80.0, "note": "frequent winter weather"}],
    "reasoning": ["Ranked by winter score."],
    "assumptions": ["Exposure = 5-year climate."],
    "confidence": "high",
}


def tool_call(name, tool_input, call_id="call_1"):
    block = SimpleNamespace(type="tool_use", id=call_id, name=name, input=tool_input)
    return SimpleNamespace(stop_reason="tool_use", content=[block])


def final_answer(data=FINAL):
    block = SimpleNamespace(type="text", text=json.dumps(data))
    return SimpleNamespace(stop_reason="end_turn", content=[block])


class FakeClient:
    """Mimics client.beta.messages.create, returning responses in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.responses.pop(0)


@pytest.fixture
def fake_tools(monkeypatch):
    calls = []

    def fake_run_tool(name, tool_input):
        calls.append((name, tool_input))
        return '{"ok": true}', False

    monkeypatch.setattr(tools, "run_tool", fake_run_tool)
    return calls


def test_agent_runs_tool_then_returns_validated_answer(fake_tools):
    client = FakeClient([tool_call("rank_hubs", {"category": "winter"}), final_answer()])
    answer = agent.Agent(client).ask("Which Midwest hubs are most exposed to winter?")

    assert fake_tools == [("rank_hubs", {"category": "winter"})]
    assert answer.ranking[0].hub_id == "minneapolis"
    assert answer.confidence == "high"
    # The tool result was sent back, matched to the tool call id.
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "call_1"


def test_agent_sends_schema_and_tools(fake_tools):
    client = FakeClient([final_answer()])
    agent.Agent(client).ask("hi")
    request = client.requests[0]
    assert request["model"] == agent.MODEL
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["tools"] == tools.TOOL_DEFINITIONS


def test_follow_up_question_includes_history(fake_tools):
    client = FakeClient([final_answer(), final_answer()])
    chat = agent.Agent(client)
    chat.ask("Rank the Midwest hubs for winter.")
    chat.ask("And in the South?")
    sent = client.requests[1]["messages"]
    assert sent[0]["content"] == "Rank the Midwest hubs for winter."
    assert sent[-1]["content"] == "And in the South?"


def test_invalid_answer_raises_and_is_forgotten(fake_tools):
    bad = {**FINAL, "confidence": "very sure"}   # not low/medium/high
    chat = agent.Agent(FakeClient([final_answer(bad)]))
    with pytest.raises(agent.AgentError):
        chat.ask("hi")
    assert chat.messages == []


def test_agent_stops_after_too_many_tool_rounds(fake_tools):
    rounds = [tool_call("list_hubs", {}) for _ in range(agent.MAX_TOOL_ROUNDS)]
    with pytest.raises(agent.AgentError):
        agent.Agent(FakeClient(rounds)).ask("loop forever")


def test_schema_forbids_extra_fields():
    schema = agent.ANSWER_FORMAT["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(FINAL)
