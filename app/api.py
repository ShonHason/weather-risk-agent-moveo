"""The HTTP API that the chat interface uses.

    uvicorn app.api:app --reload      # then open http://127.0.0.1:8000/docs

Endpoints:
    POST /chat     ask the agent; send the same session_id for follow-ups
    GET  /hubs     the list of hubs
    GET  /scores   the deterministic risk ranking (no LLM involved)
"""

import uuid
from typing import Literal, Optional

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import tools
from app.agent import Agent, AgentError
from app.env import load_env
from app.schemas import FinalAnswer

load_env()

app = FastAPI(title="Weather Risk Intelligence Agent")

# One Agent (= one conversation) per session, kept in memory.
sessions = {}

Category = Literal["winter", "hurricane", "flood", "severe_storm", "heat"]
Region = Literal["Northeast", "Midwest", "South", "West"]


class ChatRequest(BaseModel):
    message: str = Field(pattern=r"\S")   # must contain some non-space text
    session_id: Optional[str] = None   # omit to start a new conversation


class ChatResponse(BaseModel):
    session_id: str
    answer: FinalAnswer


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = Agent()
    try:
        answer = sessions[session_id].ask(request.message)
    except AgentError as error:
        raise HTTPException(status_code=502, detail=f"Agent error: {error}")
    except (anthropic.APIConnectionError, anthropic.RateLimitError,
            anthropic.InternalServerError) as error:
        # Temporary: Claude is unreachable, busy or down. Retrying may work.
        raise HTTPException(status_code=503, detail=f"Claude API unavailable: {error}")
    except anthropic.APIError as error:
        # Claude rejected our request: a bug on our side, not an outage.
        raise HTTPException(status_code=502, detail=f"Claude API error: {error}")
    return ChatResponse(session_id=session_id, answer=answer)


@app.get("/hubs")
def hubs(region: Optional[Region] = None):
    return tools.list_hubs(region)


@app.get("/scores")
def scores(category: Optional[Category] = None, region: Optional[Region] = None):
    return tools.rank_hubs(category=category, region=region)
