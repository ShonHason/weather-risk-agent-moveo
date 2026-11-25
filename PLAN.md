# Plan

## Decisions
- **LLM:** Claude (official Anthropic SDK), raw tool-use loop, no agent framework.
- **Structured output:** Pydantic models → JSON schema, validated in code.
- **Data:**
  - FEMA National Risk Index (NRI): county-level hazard exposure scores. Main input to the risk score.
  - Open-Meteo Archive: observed daily weather (snow, rain, wind, temperature). Used for weather statistics and as supporting evidence.
  - OpenFEMA disaster declarations: optional extension, context only, never part of the score (avoids double counting with NRI).
- **Scoring:** deterministic. Five hazard categories, each 0–100, combined with weights from one config file.
  - Winter: winter weather, ice storm, cold wave
  - Hurricane: hurricane
  - Flood: riverine flood, coastal flood
  - Severe storm: tornado, strong wind, hail
  - Heat: heat wave
- **Storage:** SQLite (API cache and score history).
- **API:** FastAPI. **UI:** a single HTML page served by FastAPI.
- **Chat memory:** in memory, keyed by `session_id`.
- **Eval:** deterministic checks (tool used, ranking order, numbers within tolerance).

## Assumptions
- Hubs are fictional, located in real US cities. Defined in `data/hubs.json`. Adding a hub = adding one line (name, city, state, lat, lon, county FIPS). Region is derived from the state (US Census regions).
- Exposure means long-term climate: 5 years of history. Forecasts are out of scope.
- "Last year" means the previous calendar year (2025).
- Voice is out of scope.

## Steps
1. **Skeleton:** git init, `.gitignore`, `requirements.txt`, `.env.example`, `scripts/test.py`, `data/hubs.json`, README.md and DESIGN.md stubs.
2. **Data clients and cache:** NRI client (verify the official FEMA service URL; fallback is the bundled county CSV), Open-Meteo client, SQLite cache.
3. **Metrics and scoring:** per-hub weather metrics and the deterministic risk score, with a breakdown per hazard.
4. **Agent:** Claude tool-use loop. Tools: `list_hubs`, `get_hub_metrics`, `rank_hubs`, `compare_hubs`. Final answer follows a Pydantic schema (answer, ranking, reasoning, assumptions, confidence). Small command-line chat for manual testing.
5. **API:** `POST /chat` (with `session_id`), `GET /hubs`, `GET /scores`.
6. **Chat UI:** a single HTML page that calls `/chat`.
7. **Eval set:** about 10 questions with expected checks, and a runner script.
8. **Wrap-up:** finish README.md and DESIGN.md, then DESCRIPTION.md.
   Optional, only if time is left, in this order:
   - OpenFEMA `get_disaster_history` tool (context only)
   - Alert when a hub's risk score changes (bonus)
   - Deploy to a URL

## Reminder
- Export the full session with the AI agent at the end (mandatory deliverable).
