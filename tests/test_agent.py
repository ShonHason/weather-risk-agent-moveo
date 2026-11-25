"""Tests for the agent loop. Claude is replaced by a fake client that returns
scripted responses, so no API calls are made."""

import json
from types import SimpleNamespace

import pytest

from app import agent, tools

FINAL = {
    "answer": "Minneapolis is most exposed.",
    "ranking": [{"hub_id": "minneapolis", "hub_name": "Minneapolis Hub",
                 "category": "winter", "score": 80.0, "note": "frequent winter weather"}],
    "reasoning": ["Ranked by winter score."],
    "assumptions": ["Exposure = 5-year climate."],
    "confidence": "high",
    "complete": True,
}


USAGE = SimpleNamespace(input_tokens=100, output_tokens=20)


def tool_call(name, tool_input, call_id="call_1"):
    block = SimpleNamespace(type="tool_use", id=call_id, name=name, input=tool_input)
    return SimpleNamespace(stop_reason="tool_use", content=[block], usage=USAGE)


def final_answer(data=FINAL):
    block = SimpleNamespace(type="text", text=json.dumps(data))
    return SimpleNamespace(stop_reason="end_turn", content=[block], usage=USAGE)


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


def test_agent_logs_tool_calls_per_turn(fake_tools):
    client = FakeClient([tool_call("list_hubs", {}), final_answer(), final_answer()])
    chat = agent.Agent(client)
    chat.ask("first")
    chat.ask("second")
    assert chat.tool_log == [{"turn": 1, "name": "list_hubs", "input": {},
                              "output": '{"ok": true}', "is_error": False}]
    assert chat.turn == 2


def test_incomplete_answer_gets_one_retry(fake_tools):
    unfinished = {**FINAL, "answer": "I'll rank the Northeast next.", "complete": False}
    client = FakeClient([final_answer(unfinished),
                         tool_call("rank_hubs", {"region": "Northeast"}), final_answer()])
    chat = agent.Agent(client)
    answer = chat.ask("And in the Northeast?")
    assert answer.complete and answer.answer == FINAL["answer"]
    assert chat.retries == 1
    assert client.requests[1]["messages"][-1] == {"role": "user", "content": agent.INCOMPLETE_NUDGE}
    assert fake_tools == [("rank_hubs", {"region": "Northeast"})]


def test_still_incomplete_after_retry_raises(fake_tools):
    unfinished = {**FINAL, "complete": False}
    chat = agent.Agent(FakeClient([final_answer(unfinished), final_answer(unfinished)]))
    with pytest.raises(agent.AgentError, match="incomplete"):
        chat.ask("hi")
    assert chat.messages == []


def test_agent_sends_schema_and_tools(fake_tools):
    client = FakeClient([final_answer()])
    agent.Agent(client).ask("hi")
    request = client.requests[0]
    assert request["model"] == agent.DEFAULT_MODEL == "claude-haiku-5-5"
    assert "fallbacks" not in request          # Haiku has no refusal fallback
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["tools"] == tools.TOOL_DEFINITIONS


def test_model_comes_from_env_and_opus_gets_fallback(fake_tools, monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "claude-opus-5-5")
    monkeypatch.setenv("AGENT_EFFORT", "high")
    client = FakeClient([final_answer()])
    chat = agent.Agent(client)
    chat.ask("hi")
    assert client.requests[0]["model"] == "claude-opus-5-5"
    assert client.requests[0]["output_config"]["effort"] == "high"
    assert client.requests[0]["fallbacks"] == "default"    # Opus supports it
    assert chat.usage == {"input_tokens": 100, "output_tokens": 20}


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
