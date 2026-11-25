"""The HTTP API that the chat interface uses.

    uvicorn app.api:app --reload      # then open http://127.0.0.1:8000/docs

Endpoints:
    GET  /         the chat page (app/static/index.html)
    POST /chat     ask the agent; send the same session_id for follow-ups
    GET  /hubs     the list of hubs
    GET  /scores   the deterministic risk ranking (no LLM involved)
    POST /alerts/check  recompute short-term scores, alert on changes
                        (header X-Alert-Token must equal ALERT_TOKEN)
    GET  /alerts   the most recent alerts
"""

import os
import secrets
import uuid
from pathlib import Path
from typing import Literal, Optional

import anthropic
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import alerts, tools
from app.agent import Agent, AgentError
from app.env import load_env
from app.schemas import FinalAnswer

load_env()

CHAT_PAGE = Path(__file__).parent / "static" / "index.html"

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


@app.get("/", include_in_schema=False)
def chat_page():
    return FileResponse(CHAT_PAGE)


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


@app.post("/alerts/check")
def check_alerts(x_alert_token: Optional[str] = Header(default=None)):
    """The webhook that triggers a risk-change check. Call it from a scheduler."""
    expected = os.environ.get("ALERT_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="ALERT_TOKEN is not set on the server")
    if not secrets.compare_digest(x_alert_token or "", expected):
        raise HTTPException(status_code=401, detail="Missing or wrong X-Alert-Token")
    try:
        return alerts.run_check()
    except OSError as error:   # network error or HTTP error code
        raise HTTPException(status_code=503, detail=f"Forecast API unavailable: {error}")


@app.get("/alerts")
def list_alerts(limit: int = Query(default=50, ge=1, le=500)):
    return alerts.list_alerts(limit=limit)
