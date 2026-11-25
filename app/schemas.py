"""The structured answer the agent must return (JSON schema enforced).

The schema is sent to Claude as the required output format, and every reply
is validated again in code with Pydantic before we use it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RankedHub(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hub_id: str
    hub_name: str
    category: Literal["overall", "winter", "hurricane", "flood", "severe_storm", "heat"] = Field(
        description="What the score measures: the overall score or one category."
    )
    score: float = Field(description="The score this hub was ranked by (0-100).")
    note: str = Field(description="One short line: what drives this hub's score.")


class FinalAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(description="Direct answer to the question, in plain English.")
    ranking: list[RankedHub] = Field(
        description="Hubs in order, highest risk first. Empty if the question "
                    "is not a ranking or comparison."
    )
    reasoning: list[str] = Field(
        description="Short steps explaining how the answer follows from the tool data."
    )
    assumptions: list[str] = Field(
        description="Assumptions and scope limits that affect this answer."
    )
    confidence: Literal["low", "medium", "high"]
    complete: bool = Field(
        description="true if this answers the question with data already fetched. "
                    "false if you still need to call a tool to answer it."
    )
