# Design

Work in progress. Filled in as the steps are built. See PLAN.md for the agreed decisions.

## System architecture

```
 chat UI / curl
      |  HTTP: POST /chat, GET /hubs, GET /scores
      v
 FastAPI (app/api.py) -- one Agent per session_id, in memory
      |
      v
 Agent (app/agent.py) ---- conversation + tools + answer schema ----> Claude API
      ^                 <--- tool calls / final JSON answer ---------
      |
      | runs tool calls
      v
 Tools (app/tools.py): list_hubs, get_hub_metrics, rank_hubs, compare_hubs
      |
      v
 Scoring (scoring.py, metrics.py) --> clients (nri.py, weather.py)
                                          |
                                          v
                              SQLite cache <-- FEMA NRI / Open-Meteo APIs
```

- **Claude decides, code computes.** Claude picks which tools to call and
  writes the explanation; every score, metric and ranking comes from our
  deterministic Python code. The system prompt forbids Claude from
  calculating any number itself (no averages, differences or ratios): it may
  only quote numbers the tools returned. So the tools return the derived
  numbers a question needs, e.g. `compare_hubs` returns each hub's average
  over the chosen categories and the highest hub per category. Why: an LLM's
  arithmetic is not reliably correct, and a number we didn't compute can't
  be traced or tested.
- **Agent loop** (hand-written, no framework): send the conversation, run the
  tools Claude asks for, send the results back, repeat until Claude returns
  its final answer. Capped at 8 tool rounds.
- **Structured output.** The final answer must follow the `FinalAnswer`
  JSON schema (`app/schemas.py`: answer, ranking, reasoning, assumptions,
  confidence). The schema is sent to the API as the required output format,
  and the reply is validated again with Pydantic. An invalid answer raises an
  error instead of reaching the user.
- **Conversation memory.** One `Agent` object keeps one conversation's full
  history, so follow-up questions work. A failed turn is removed from the
  history.
- **Model.** `claude-opus-5-5`, effort `medium` (enough for 1-3 tool calls and
  a short explanation). Server-side refusal fallback is on: if a safety check
  declines a request, the API retries it on a fallback model.
- **API** (`app/api.py`, FastAPI): `POST /chat` takes `{message, session_id?}`
  and returns `{session_id, answer}`; without a `session_id` a new
  conversation starts. `GET /hubs` and `GET /scores` return the hubs and the
  deterministic ranking directly, with no LLM involved, so the numbers can be
  checked independently of the agent. Errors: invalid input -> 422, agent
  produced no valid answer or Claude rejected the request -> 502, Claude
  API unreachable, rate-limited or down (worth retrying) -> 503.
- **Ranking entries name their category** (`overall`, `winter`, ...), so a
  comparison across hazards (e.g. Miami vs Houston on hurricane and flood)
  is unambiguous.
- **Tools return breakdowns, not just scores**, so Claude can explain *why*
  (e.g. "Detroit's ice storms are more frequent than in 98% of counties").

## Repository structure

```
app/            application code
  hubs.py       loads data/hubs.json and adds each hub's region
  fetch.py      downloads JSON from public APIs, through the cache
  cache.py      SQLite key-value cache for API responses
  nri.py        FEMA National Risk Index client (hazard frequency per county)
  weather.py    Open-Meteo client (daily weather history)
  metrics.py    daily weather -> metrics (snow days, hot days, ...) per hub
  scoring.py    the deterministic risk score, breakdown and ranking
  scoring_config.py  all weights, scales and thresholds of the score
  tools.py      the 4 tools Claude can call, and their definitions
  schemas.py    FinalAnswer: the JSON schema of the agent's answer
  agent.py      the Claude tool-use loop and system prompt
  api.py        FastAPI app: /chat, /hubs, /scores
  env.py        loads .env (API key)
data/
  hubs.json     the list of hubs (one line per hub)
  cache.db      SQLite cache, created on first use (not in git)
scripts/
  test.py       runs unit tests or the smoke check
  chat.py       command-line chat with the agent (manual testing)
tests/        unit tests
```

## Data sources
- **FEMA National Risk Index (NRI), December 2025 version.** Official FEMA
  ArcGIS service "National Risk Index Counties", no API key. We use each
  hazard's **annualized frequency** (`AFREQ`: events or event-days per year in
  the county) and turn it into a national percentile across all 3,232 US
  counties (downloaded once, in 2 pages, and cached). FEMA's own risk score
  (`RISKS`) is kept as context only, see "Why frequency" below.
- **Open-Meteo Historical Weather API.** No API key. Daily snowfall,
  precipitation, min/max temperature and max wind gusts for the last 5 full
  calendar years at each hub's coordinates.

## Risk score
Deterministic, 0-100, higher = more exposed. Computed in `app/scoring.py`;
every number comes from `app/scoring_config.py`.

| Category | NRI hazards, by frequency percentile (worst one counts) | Observed metric (30%) |
|---|---|---|
| Winter | winter weather, ice storm, cold wave | snow days/year, 40 = 100 |
| Heat | heat wave | days >= 35 °C/year, 60 = 100 |
| Flood | inland flooding, coastal flooding | days >= 25 mm rain/year, 15 = 100 |
| Hurricane | hurricane | none (NRI only) |
| Severe storm | tornado, strong wind, hail | none (NRI only) |

- **Chronic vs acute.** Winter, heat and heavy rain happen every year, so 5
  years of observed weather is a fair sample: score = 70% NRI + 30% observed.
  Hurricanes and tornadoes are rare in any one place, so 5 years can miss a
  location that is at constant risk: score = NRI only, since NRI is built
  from decades of event records.
- **Worst hazard per category (max).** One severe hazard is enough to shut a
  hub down; averaging would dilute it.
- **Fixed scales, not ranking between hubs.** A hub's score doesn't change
  when another hub is added, and each number can be checked by hand.
- **Overall** = equal-weighted (20%) sum of the five categories.
- **Why frequency, not FEMA's risk score.** `RISKS` measures risk to the whole
  county's community: expected loss x property and population exposed x
  social vulnerability. Big counties score near 100 on almost everything
  (Phoenix 100 for hail, Houston 89 for winter). A hub is one facility, and
  disruption is about how *often* roads and sites shut, so we use frequency.
  We also rejected NRI's loss rate (`ALR`): it measures building damage, and
  snow or heat rarely damage buildings (Buffalo's winter is in the 7th
  percentile).

Every result includes the breakdown (NRI part, worst hazard, observed metric
and value), so the agent can explain *why* a hub scores high.

## Data storage choice
**SQLite**, from the Python standard library. One file (`data/cache.db`), no
server to run. API responses are cached by request URL, so each request is
sent once: faster answers, fewer API calls, and the demo keeps working if an
API is slow. JSON files would work too, but SQLite also fits the planned score
history. Postgres would be overkill for one process and a few MB of data.

## Assumptions
- Hubs are fictional, located in real US cities.
- Regions follow the US Census Bureau definition (Northeast, Midwest, South, West).
- A hub's hazard exposure is how often each hazard happens in its county (NRI frequency).
- Weather is taken at the hub's coordinates (Open-Meteo grid, ~10 km).

## Limitations
- Conversation history lives in memory: it is lost when the server
  restarts, sessions never expire, and it works for one server process only.
  Two requests in the same session at the same moment are not guarded.
- The agent answers only from our hubs and data; it cannot fetch forecasts
  or other sources.
- The observed-weather scales (e.g. 40 snow days = 100) are judgment calls.
  They are one line each in `app/scoring_config.py`.
- Heavy rain is only a partial proxy for flooding (it misses storm surge and
  river floods from upstream); NRI covers those in the other 70%.
- Open-Meteo is modelled (reanalysis) data on a ~10 km grid. It can differ
  from a local weather station, e.g. it underestimates short tropical
  downpours and may count snow from nearby hills.
- NRI frequency counts events anywhere in the county, so large or
  mountainous counties get more events (e.g. Seattle's King County includes
  the Cascades).
- Frequency ignores severity: a weak and a strong event count the same.
- Open-Meteo's free tier is rate-limited; a 429 response is retried after 30 s.
- The cache never expires. That is fine for historical data, but NRI updates
  about once a year: delete `data/cache.db` to refresh.
