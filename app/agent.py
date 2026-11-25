"""The agent: a Claude tool-use loop with a structured final answer.

One Agent = one conversation. It keeps the message history, so follow-up
questions ("and in the South?") work.

How one question is answered:
  1. Send the conversation + tool definitions + answer schema to Claude.
  2. If Claude asks for tools, run them (app/tools.py) and send the results.
  3. Repeat until Claude gives its final answer, which must match the
     FinalAnswer JSON schema. We validate it again with Pydantic.
"""

from datetime import date

import anthropic

from app import scoring_config as config
from app import tools
from app.schemas import FinalAnswer

MODEL = "claude-opus-5-5"
MAX_TOOL_ROUNDS = 8   # safety limit: a normal question needs 1-3 rounds

LAST_YEAR = date.today().year - 1

SYSTEM_PROMPT = f"""\
You are a weather risk analyst for a US logistics company. Analysts ask you
which distribution hubs are most exposed to weather disruption, to decide
where to invest in resilience upgrades.

Only use numbers returned by the tools. Never calculate a new number
yourself: no averages, sums, differences, ratios or percentages, and never
invent or estimate a score, metric or ranking. If you need a number the tools
don't return, compare in words instead: "much more frequent", not
"twice as frequent". If the tools can't answer something, say so.

How the risk score works (computed by the tools, 0-100, higher = more exposed):
- Five categories: winter, hurricane, flood, severe_storm, heat. Overall score
  = equal-weighted (20% each) average of the five.
- NRI part: how often each hazard happens in the hub's county per year (FEMA
  National Risk Index annualized frequency), as a national percentile across
  all US counties. A category takes its worst hazard.
- Winter, heat and flood also use observed weather from the last 5 full years
  (Open-Meteo): score = 70% NRI + 30% observed (snow days, days >= 35 C,
  days >= 25 mm rain per year). Hurricane and severe storm are NRI only,
  because rare events don't show up reliably in 5 years of weather.

Weather metric definitions (daily values):
- snow day: snowfall >= {config.SNOW_DAY_MIN_CM} cm
- hot day: max temperature >= {config.HOT_DAY_MIN_C} C
- heavy rain day: precipitation >= {config.HEAVY_RAIN_MIN_MM} mm
- freezing day: min temperature < {config.FREEZING_DAY_MAX_C} C
- windy day: max wind gust >= {config.WINDY_DAY_MIN_KMH} km/h

Conventions:
- "Last year" means {LAST_YEAR}. "Exposure" means long-term climate, not
  forecasts; forecasts are out of scope.
- "Winter disruption" -> category winter; "storms" -> severe_storm (tornado,
  strong wind, hail); "flooding" -> flood; "heat" -> heat.
- Hubs are fictional sites in real US cities; data is at county level for NRI
  and at the hub's coordinates (~10 km grid) for weather.

Your final answer:
- answer: direct and short, with the key numbers.
- ranking: fill it for rankings and comparisons, otherwise leave it empty.
  Each entry is one hub's score in one category (or "overall"); a comparison
  across several categories has one entry per hub and category.
- reasoning: how the numbers lead to the answer (which hazards drive it).
- assumptions: the conventions and data limits that matter for this answer.
- confidence: high when the tools answer the question directly; medium when
  you had to interpret the question; low when the data only partly covers it.
"""

ANSWER_FORMAT = {"type": "json_schema", "schema": FinalAnswer.model_json_schema()}


class AgentError(Exception):
    """The agent could not produce a valid answer."""


class Agent:
    def __init__(self, client=None):
        self.client = client or anthropic.Anthropic()
        self.messages = []   # the whole conversation, sent on every request

    def ask(self, question):
        """Answer one question (with the conversation so far). Returns FinalAnswer."""
        history_length = len(self.messages)
        self.messages.append({"role": "user", "content": question})
        try:
            return self._run_loop()
        except Exception:
            # Forget the failed turn, so the next question starts clean.
            del self.messages[history_length:]
            raise

    def _run_loop(self):
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=tools.TOOL_DEFINITIONS,
                messages=self.messages,
                output_config={"effort": "medium", "format": ANSWER_FORMAT},
                # If a safety check declines a request, retry it on a
                # fallback model instead of failing.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            # Keep the full content (including thinking blocks) in history.
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                self.messages.append({"role": "user", "content": self._run_tools(response)})
            elif response.stop_reason == "end_turn":
                return self._parse_answer(response)
            else:
                raise AgentError(f"Claude stopped early: {response.stop_reason}")

        raise AgentError(f"No final answer after {MAX_TOOL_ROUNDS} tool rounds")

    def _run_tools(self, response):
        """Run every tool call in the response. All results go back in one message."""
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output, is_error = tools.run_tool(block.name, block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": is_error,
                })
        return results

    def _parse_answer(self, response):
        """Validate the final JSON against the FinalAnswer schema."""
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            return FinalAnswer.model_validate_json(text)
        except ValueError as error:
            raise AgentError(f"Answer did not match the schema: {error}") from error
