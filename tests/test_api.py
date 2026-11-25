"""Tests for the API, over HTTP with FastAPI's TestClient.
A fake Agent replaces Claude, so no API calls are made."""

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from app import api, tools
from app.agent import AgentError
from app.schemas import FinalAnswer

http = TestClient(api.app)


class FakeAgent:
    """Answers with the question count, so we can see the history is kept."""

    def __init__(self):
        self.questions = []

    def ask(self, message):
        if message == "break":
            raise AgentError("bad answer")
        if message == "offline":
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
        self.questions.append(message)
        return FinalAnswer(answer=f"answer {len(self.questions)}", ranking=[],
                           reasoning=[], assumptions=[], confidence="high")


@pytest.fixture(autouse=True)
def fake_agent(monkeypatch):
    monkeypatch.setattr(api, "Agent", FakeAgent)
    monkeypatch.setattr(api, "sessions", {})


def ask(message, session_id=None):
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    return http.post("/chat", json=body)


def test_chat_starts_a_new_session():
    response = ask("hi")
    assert response.status_code == 200
    assert response.json()["session_id"]
    assert response.json()["answer"]["answer"] == "answer 1"


def test_same_session_keeps_the_conversation():
    first = ask("rank the Midwest").json()
    second = ask("and the South?", first["session_id"]).json()
    assert second["session_id"] == first["session_id"]
    assert second["answer"]["answer"] == "answer 2"
    other = ask("hi").json()
    assert other["session_id"] != first["session_id"]
    assert other["answer"]["answer"] == "answer 1"


def test_blank_or_missing_message_is_rejected():
    assert ask("   ").status_code == 422
    assert http.post("/chat", json={}).status_code == 422


def test_agent_error_is_502_and_claude_outage_is_503():
    assert ask("break").status_code == 502
    assert ask("offline").status_code == 503


def test_hubs_filters_by_region():
    response = http.get("/hubs", params={"region": "West"})
    assert response.status_code == 200
    assert {h["region"] for h in response.json()} == {"West"}
    assert http.get("/hubs", params={"region": "Mars"}).status_code == 422


def test_scores_passes_filters_to_rank_hubs(monkeypatch):
    monkeypatch.setattr(tools, "rank_hubs",
                        lambda category=None, region=None: {"ranked_by": category, "region": region})
    response = http.get("/scores", params={"category": "heat", "region": "South"})
    assert response.json() == {"ranked_by": "heat", "region": "South"}
    assert http.get("/scores", params={"category": "volcano"}).status_code == 422


def test_chat_page_is_served():
    response = http.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'fetch("/chat"' in response.text
