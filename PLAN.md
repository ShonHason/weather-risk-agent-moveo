# Plan

## Decisions
- **LLM:** Claude (official Anthropic SDK), raw tool-use loop, no agent framework.
  - Model `claude-opus-5-5`, effort `medium`, server-side refusal fallback on.
  - Final answer: JSON schema sent as the API's output format, then validated with Pydantic.
  - `.env` is read by a small helper (`app/env.py`), no `python-dotenv`.
- **Structured output:** Pydantic models → JSON schema, validated in code.
- **Data:**
  - FEMA National Risk Index (NRI): county-level hazard data. Main input to the risk score: each hazard's annualized frequency (`AFREQ`) as a national percentile across all US counties. FEMA's `RISKS` score is context only (it is biased toward large counties).
  - Open-Meteo Archive: observed daily weather (snow, rain, wind, temperature). Used for weather statistics and as supporting evidence.
  - OpenFEMA disaster declarations: optional extension, context only, never part of the score (avoids double counting with NRI).
- **Scoring:** deterministic. Five hazard categories, each 0–100, combined with equal weights (20% each) from one config file (`app/scoring_config.py`).
  - Category NRI score = the worst (max) hazard frequency percentile in the category. Not-applicable hazards count as 0.
  - Chronic categories (winter, heat, flood) = 70% NRI + 30% observed weather (snow days / hot days / heavy-rain days per year, on a fixed linear 0–100 scale).
  - Acute categories (hurricane, severe storm) = NRI only: rare events don't show up reliably in 5 years of weather, and NRI is built from decades of event records.
  - Winter: winter weather, ice storm, cold wave
  - Hurricane: hurricane
  - Flood: riverine flood, coastal flood
  - Severe storm: tornado, strong wind, hail
  - Heat: heat wave
- **Storage:** SQLite (API cache and score history).
- **API:** FastAPI, run with uvicorn. Server creates a `session_id` when none is sent. **UI:** a single HTML page served by FastAPI.
- **Chat memory:** in memory, keyed by `session_id`.
- **Numbers come only from code.** Claude may only use numbers returned by tools, never calculate new ones (system prompt rule). Tools return the derived numbers analysts need (e.g. `compare_hubs` returns averages and the highest hub per category).
- **Tests:** pytest; `httpx` approved as a test-only dependency for API tests.
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
