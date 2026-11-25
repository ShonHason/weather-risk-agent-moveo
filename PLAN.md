# Plan

## Decisions
- **LLM:** Claude (official Anthropic SDK), raw tool-use loop, no agent framework.
  - Model `claude-haiku-5-5` by default (chosen by eval: ~46x cheaper, ~2x faster, same pass rate after fixes); `claude-opus-5-5` via `AGENT_MODEL`. Effort `medium` (`AGENT_EFFORT`; `high` measured: slower, no gain). Refusal fallback only for models that support it (Opus).
  - `FinalAnswer.complete`: an answer marked incomplete gets one automatic retry, then a clear error.
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
- **Numbers come only from code.** Claude may only use numbers returned by tools, never calculate new ones (system prompt rule). Tools return the derived numbers analysts need: hub count, gaps between consecutive ranked hubs, score ranges, pair gaps (positive, naming the higher hub), averages, highest hub, and ratios of yearly counts only (never of 0-100 scores). The prompt states the data period.
- **Short-term alert (Step 9):** a second deterministic score from the Open-Meteo 7-day forecast, separate from the long-term score. Per hazard (snow, heavy rain, wind gusts, heat, extreme cold) the worst forecast day on a linear scale (config in `app/scoring_config.py`); hub score = worst hazard. `POST /alerts/check` (header `X-Alert-Token` = `ALERT_TOKEN`) recomputes all hubs, compares with the last check, alerts on a change of >= 10 points, stores scores and alerts in `data/history.db` (separate from the cache, so clearing the cache keeps history), and POSTs alerts as generic JSON to `ALERT_WEBHOOK_URL` if set. `GET /alerts` lists them. First run = baseline. Scheduling stays outside the app (cron). Forecasts are never cached.
- **Alert comparison (Step 10):** every check is stored (`score_history`). A hub alerts when its score is >= 10 points from any of its scores in the last 3 days (`ALERT_WINDOW_DAYS`), counting only checks since its last alert (no repeats); so a gradual rise alerts too. No check in the window: compare with the last check. Only when the old or new score is >= 40 (`ALERT_MIN_LEVEL`), so moves between low scores are not alerts. Each alert shows what it was compared with (score, time, driving hazard), and alerts are sorted by size of change.
- **Forecast vs normal (Step 11):** each forecast day's hazard also gets a relative score: its percentile among the hub's own 2021-2025 days of the same calendar month (cached history, no new API calls), 0 up to the 95th percentile, 100 beyond the most extreme day in the history. It counts only on a disruptive day, by the long-term daily definitions (snow day, heavy rain >= 25 mm, gusts >= 60 km/h, max >= 35 °C, min < 0 °C). Hazard score = max(absolute, relative): -8 °C counts in Dallas, not in Minneapolis. An unusual day (>= 95th percentile) that is not disruptive becomes an info note in the forecast tool and the alert details; it never raises the score or triggers an alert. (Measured on a live forecast: 90th percentile + low thresholds put 16 of 21 hubs >= 40; this version 12; absolute only 10.)
- **Deployment (Step 12):** Render free web service from `render.yaml`. The build fills the data cache (`python -m app.scoring`) so the first question is fast; forecasts stay live. Secrets (`ANTHROPIC_API_KEY`, `ALERT_WEBHOOK_URL`) are set in the Render dashboard; `ALERT_TOKEN` is generated by Render. Chat is open (no password); protection = a monthly spend limit in the Anthropic console (Haiku ~$0.001 per question). Dependencies pinned. Free plan: sleeps after ~15 min idle (first request ~30-60 s), disk wiped on restart (chat sessions and alert history reset).
- **No scheduled weather scan (decided):** a scheduled check (cron / GitHub Actions calling `POST /alerts/check`) was considered and dropped: on the free plan the history is wiped whenever the server sleeps, so every scheduled check would only save a baseline and never alert, and in the interview a schedule shows nothing that can be watched live. The alert is shown with `scripts/demo_alerts.py` and a manual `POST /alerts/check` instead. Real scheduling needs persistent storage (paid disk or an external database) and one scheduler entry.
- **Tests:** pytest; `httpx` approved as a test-only dependency for API tests.
- **Eval:** 25 cases in `evals/cases.json`, deterministic checks only (no LLM judge). Expected values are computed by our code at eval time. Every case also checks: scores match the tools, no number the tools didn't return (incl. own round thresholds like "above 85"), no ratio wording. `--repeat N` measures pass rates. `rank_hubs` returns min/max score ranges so summaries can use real numbers.

## Assumptions
- Hubs are fictional, located in real US cities. Defined in `data/hubs.json`. Adding a hub = adding one line (name, city, state, lat, lon, county FIPS). Region is derived from the state (US Census regions).
- Exposure means long-term climate: 5 years of history. Forecasts are used only for the short-term alert score (and its agent tool).
- "Last year" means the previous calendar year (2025).
- Voice is out of scope.

## Steps
1. **Skeleton:** git init, `.gitignore`, `requirements.txt`, `.env.example`, `scripts/test.py`, `data/hubs.json`, README.md and DESIGN.md stubs.
2. **Data clients and cache:** NRI client (verify the official FEMA service URL; fallback is the bundled county CSV), Open-Meteo client, SQLite cache.
3. **Metrics and scoring:** per-hub weather metrics and the deterministic risk score, with a breakdown per hazard.
4. **Agent:** Claude tool-use loop. Tools: `list_hubs`, `get_hub_metrics`, `rank_hubs`, `compare_hubs`. Final answer follows a Pydantic schema (answer, ranking, reasoning, assumptions, confidence). Small command-line chat for manual testing.
5. **API:** `POST /chat` (with `session_id`), `GET /hubs`, `GET /scores`.
6. **Chat UI:** a single HTML page that calls `/chat`.
7. **Eval set:** 24 questions (assignment, rankings, single numbers, follow-ups, traps) with expected checks, and a runner script.
8. **Wrap-up:** finish README.md and DESIGN.md, then DESCRIPTION.md.
   Optional, only if time is left, in this order:
   - OpenFEMA `get_disaster_history` tool (context only)
   - Alert when a hub's risk score changes (bonus): now Step 9
   - Deploy to a URL: now Step 12
9. **Short-term risk alert:** forecast score, `POST /alerts/check`, `GET /alerts`, outgoing webhook. Then, if time allows, one agent tool for the forecast score ("what's the risk at Chicago this week?").
10. **Alert over a window:** catch gradual rises over the last 3 days, minimum level, show the previous driver, sort by change.
11. **Forecast vs normal:** relative score per hub and month from the cached history, combined with the absolute score (max).
12. **Deploy:** Render free web service (`render.yaml`), pinned dependencies, docs. No scheduled scan (see Decisions).
13. **Team channel link:** optional `ALERT_CHANNEL_URL`; each alert's text ends with a Slack link "Discuss in the team channel" (chosen over a link to the web chat). The chat page gets a round Slack-logo button (hover: "Team's Slack") to the same channel, via `GET /team-channel`.

## Reminder
- Export the full session with the AI agent at the end (mandatory deliverable).
