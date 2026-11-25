# Design

How the Weather Risk Intelligence Agent is built, and why. Setup and
commands are in README.md; the step-by-step decisions are in PLAN.md.

## System architecture

```
 chat page (app/static/index.html) / curl     scheduler (cron, ...)
      |  HTTP: POST /chat, GET /hubs, GET /scores      | POST /alerts/check
      v                                                v
 FastAPI (app/api.py) -- one Agent per session_id, in memory
      |
      v
 Agent (app/agent.py) ---- conversation + tools + answer schema ----> Claude API
      ^                 <--- tool calls / final JSON answer ---------
      |
      | runs tool calls
      v
 Tools (app/tools.py): list_hubs, get_hub_metrics, rank_hubs, compare_hubs,
      |                get_forecast_risk
      v
 Scoring (scoring.py, metrics.py) --> clients (nri.py, weather.py)
      |                                   |
      |                                   v
      |                       SQLite cache <-- FEMA NRI / Open-Meteo archive
      |
 Short-term score (forecast.py) <-- Open-Meteo forecast (never cached)
      ^
      |
 Alerts (alerts.py) --> data/history.db (score history + alerts)
                    --> ALERT_WEBHOOK_URL (outgoing JSON POST)
```

(The FastAPI app also serves `POST /alerts/check` and `GET /alerts`, which
call `alerts.py`.)

- **Claude decides, code computes.** Claude picks which tools to call and
  writes the explanation; every score, metric and ranking comes from our
  deterministic Python code. The system prompt forbids Claude from
  calculating any number itself (no averages, differences or ratios): it may
  only quote numbers the tools returned. So the tools return the derived
  numbers a question needs:
  - `list_hubs`: the hub count;
  - `rank_hubs`: each hub's gap to the next hub, and the min/max score of
    the returned hubs ("between 85.8 and 98.9");
  - `compare_hubs`: each hub's average over the chosen categories, the
    highest hub per category, the gap between every pair (always positive,
    naming the higher hub, so Claude never flips a sign), and **ratios of
    yearly counts** (weather days, hazard events per year: "2.6 times as
    many heavy-rain days"). There are no ratios of the 0-100 scores: they
    are percentiles, and a ratio of percentiles has no meaning;
  - the system prompt states the exact data period (2021-01-01 to
    2025-12-31), so Claude doesn't work out years either.

  Why: an LLM's arithmetic is not reliably correct, and a number we didn't
  compute can't be traced or tested. The eval showed that a prompt rule
  alone was not enough (both models occasionally computed gaps, ratios,
  counts and round thresholds); giving the tools the numbers fixed it.
- **Agent loop** (hand-written, no framework): send the conversation, run the
  tools Claude asks for, send the results back, repeat until Claude returns
  its final answer. Capped at 8 tool rounds.
- **Structured output.** The final answer must follow the `FinalAnswer`
  JSON schema (`app/schemas.py`: answer, ranking, reasoning, assumptions,
  confidence, complete). The schema is sent to the API as the required output
  format, and the reply is validated again with Pydantic. An invalid answer
  raises an error instead of reaching the user.
- **Completeness flag with one retry.** The eval caught the model answering
  a follow-up with a plan ("I'll rank the Northeast hubs next") instead of
  calling the tool. So `FinalAnswer` has a required `complete` field: if
  Claude marks its answer incomplete, the code asks it once more to call the
  tools and finish; if it's still incomplete, the user gets a clear error,
  never a non-answer. A retry only costs time when it happens (it happened
  mostly on follow-up questions, about 2 s extra on those).
- **Conversation memory.** One `Agent` object keeps one conversation's full
  history, so follow-up questions work. A failed turn is removed from the
  history.
- **Model: Claude Haiku 5.5 by default, Opus 5.5 as an option**
  (`AGENT_MODEL`), effort `medium` (`AGENT_EFFORT`). Chosen by eval. The
  last comparison, on the final agent code (after the completeness flag,
  count ratios and the data period in the prompt), every case 3 times:

  | | Opus 5.5, full run | Opus 5.5, re-run | Haiku 5.5 |
  |---|---|---|---|
  | Agent code | before the last fixes | final | final |
  | Cases run | all 24 of the time, 3 times each | 4 cases, 3 times each: top 5 overall, 3-hub winter comparison, difference trap, ratio trap | all 24 of the time, 3 times each |
  | Runs passed | 72/72 | 12/12 | 72/72 |
  | Checks passed | 441/441 | 72/72 | 444/444 |
  | Cost | $4.63 (~$0.064 per run) | $0.61 (~$0.05 per run) | $0.11 (~$0.0015 per run) |
  | Median response | 10.5 s | 8.5 s | 6 s |
  | Incomplete answers retried | n/a (no retry yet) | 0 | 4, all follow-ups, all answered on retry |

  The full Opus run is the same size as Haiku's (72 runs), on the code
  before the last fixes (completeness flag, count ratios, data period in
  the prompt). Opus was then re-run only on the cases those fixes were
  about, where both models had failed before. Both now pass everything
  they were given. Same-size runs: Haiku costs ~43x less per run (~46x
  when both ran the same code) and answers ~2x faster. Details in
  `docs/ai-session/session-2.md`.

  All scoring is deterministic Python, so the model only picks tools and
  explains; Haiku does that about as reliably as Opus at a fraction of the
  cost and twice the speed. Effort `high` on Haiku was also measured on
  the full eval: 71/72 runs (medium: 72/72), 7 s median (medium: 6 s),
  $0.12 per 72 runs (medium: $0.10). No quality gain, so `medium` stays. Server-side refusal
  fallback is sent only to models that support it (Opus, not Haiku).
- **API** (`app/api.py`, FastAPI): `POST /chat` takes `{message, session_id?}`
  and returns `{session_id, answer}`; without a `session_id` a new
  conversation starts. `GET /hubs` and `GET /scores` return the hubs and the
  deterministic ranking directly, with no LLM involved, so the numbers can be
  checked independently of the agent. Errors: invalid input -> 422, agent
  produced no valid answer or Claude rejected the request -> 502, Claude
  API unreachable, rate-limited or down (worth retrying) -> 503.
- **Chat page** (`app/static/index.html`, served at `/`): one file with
  plain HTML, CSS and JavaScript, so there is no build step and no frontend
  framework to explain. It calls `POST /chat` and keeps the `session_id` in
  memory for follow-ups ("New conversation" reloads the page). Each answer
  shows a neutral confidence label, the ranking as a table, and the reasoning
  and assumptions folded under "How I got this". Each score has a small bar
  coloured by risk level (same bands as `RISK_LEVELS`: Severe 80+, High 60+,
  Moderate 30+, Low), with a legend under the table, so the ranking can be
  scanned at a glance. Colour is used only for risk, never for confidence, so
  "high confidence" is not mistaken for a risk level. When every row has the
  same category, the column is dropped and the category is shown once. The
  empty page shows a short intro and the example questions as a 2×2 grid.
  Model output is inserted as
  plain text (`textContent`), never as HTML, so an answer cannot inject
  markup or scripts into the page.
- **Voice** (bonus, in the chat page only). A mic button uses the
  browser's own speech recognition (Web Speech API): the words appear in
  the text box while speaking. A spoken question gets a spoken reply: the
  browser reads the short `answer` sentence aloud (the table and reasoning
  stay on screen). Typed questions stay silent. Speech becomes text in the
  browser, so the server and the agent are unchanged and there are no new
  dependencies.
  - *Sending:* listening continues through short pauses; after 2 s of
    silence (`SILENCE_MS`) it stops and a "Sending in 3…" countdown
    (`COUNTDOWN_SECONDS`) starts. Typing or clicking the mic cancels it, so
    a misheard word can be fixed first; Enter or Send sends at once. Hands-
    free when the words are right, a chance to fix them when they aren't.
  - *Reply voice:* the browser's default voice sounds robotic, so the page
    picks the most natural English voice installed, from a short preference
    list (Edge "Natural" voices, macOS Premium/Enhanced voices, "Google US
    English", Samantha/Ava/Zoe), at a slightly slower pace. Quality depends
    on the browser and device: best in Edge, and on a Mac after downloading
    a Premium voice. A cloud text-to-speech API would sound near-human
    everywhere, but adds a key, a dependency and a cost per answer.
    Answers are read one sentence at a time, because Chrome's voices stop
    after about 15 s in one go.
  - *Stopping the reply:* while an answer is read, the mic button turns
    into a stop button (and the status line says so); clicking it or
    pressing Esc stops the reading. Asking a new question, starting to
    listen or starting a new conversation stops it too.
  - *Limits:* works in Chrome, Edge and Safari, not Firefox (the button is
    hidden where unsupported, so typing always works); needs HTTPS or
    localhost and mic permission; Chrome sends the audio to Google's speech
    service to transcribe it; English (`en-US`) only.
- **Short-term risk score and alert** (`app/forecast.py`, `app/alerts.py`).
  The long-term score barely moves (NRI updates yearly, a 5-year window
  shifts once a year), so an alert on it would almost never fire. The alert
  uses a second, short-term score from Open-Meteo's 7-day forecast instead:
  it changes daily, and it is what an operations team wants to hear about.
  - *Score:* for each hazard, the worst forecast day on a linear scale from
    "no impact" (0) to "severe" (100), capped: snow 0-15 cm/day, rain
    10-50 mm/day, gusts 40-100 km/h, max temperature 30-42 °C, min
    temperature -10 to -30 °C. The hub's score is its worst hazard (the
    same "one severe hazard is enough" logic as the long-term score). All
    scales are in `FORECAST_SCALES` in `app/scoring_config.py`.
  - *Relative to normal:* a fixed scale misses that -8 °C can shut
    Dallas, which rarely sees it, but is an ordinary night in Minneapolis. So each forecast value also gets its **percentile among
    the hub's own days of the same calendar month** in the cached 2021-2025
    history (no extra API calls): the share of past days that were less
    severe. Relative score: 0 up to the 95th percentile, 100 beyond the
    most extreme past day. A day's score is the **higher** of the absolute
    and relative scores (a blend would dilute exactly the case we want).
    - The relative score counts **only on a disruptive day**, by the same
      daily definitions as the long-term metrics: any snow, rain >= 25 mm,
      gusts >= 60 km/h, max >= 35 °C, a night below 0 °C. "Unusually mild
      for Miami" must never score.
    - Why the 95th percentile and those thresholds: measured on a live
      forecast, the first version (90th percentile, lower thresholds) put
      16 of 21 hubs at 40+, since 7 days x 5 hazards give 35 chances to
      land in the tail of a ~150-day sample. This version: 12 (absolute
      only: 10); the extra hubs are real signals, e.g. Detroit's forecast
      32 mm of rain is more than any November day in its history.
    - An unusual day (>= 95th percentile) that is **not** disruptive
      becomes an info **note** ("rain 14.4 mm is higher than 98.7% of
      November days in the hub's history, short of the disruption
      threshold"). Notes appear in the forecast tool and in alert details,
      but never raise the score or trigger an alert: disruption is what the
      score is about.
  - *Check:* `POST /alerts/check` recomputes all hubs and stores every
    score (with its driving hazard) in `score_history`. A hub alerts when
    its new score is at least 10 points (`ALERT_MIN_CHANGE`; smaller moves
    are day-to-day forecast noise) away from **any** of its scores in the
    last 3 days (`ALERT_WINDOW_DAYS`):
    - comparing with the whole window, not only the previous check,
      catches a gradual rise: 5 points a day alerts on day 2;
    - only scores since the hub's last alert count, so one change alerts
      once, not at every check until it leaves the window;
    - with no check in the window (checks paused), it compares with the
      last check;
    - the old or new score must be at least 40 (`ALERT_MIN_LEVEL`): a move
      between two low scores (14 -> 28) is not something ops acts on.

    Each alert names the score it was compared with, when, and what drove
    both scores ("now: wind 66.6 km/h on 11-27; before: heavy_rain 45 mm on
    11-26"), so the reader sees *what* changed. Alerts are sorted biggest
    change first. A hub's first check only saves a baseline.
  - *Trigger:* the endpoint is the webhook. Scheduling stays outside the
    app (cron, a cloud scheduler, a CI job): no scheduler dependency, and
    no duplicate checks when the server runs several workers. It needs the
    `X-Alert-Token` header (`ALERT_TOKEN`, compared in constant time), so
    strangers can't trigger it; with no token configured it is disabled.
    *No scheduled scan in the deployed demo (decided):* a schedule (cron
    or GitHub Actions calling the endpoint every few hours) was planned,
    then dropped. On Render's free plan the disk is wiped whenever the
    server sleeps, so every scheduled check would only save a new
    baseline and never alert, and in an interview a schedule shows
    nothing that can be watched live. The alert is demonstrated with
    `scripts/demo_alerts.py` and a manual `POST /alerts/check`. Real
    scheduling needs persistent storage (a paid disk or an external
    database) plus one scheduler entry; the code needs no change.
  - *Delivery:* every alert is saved and listed at `GET /alerts`. If
    `ALERT_WEBHOOK_URL` is set, alerts are also POSTed there as JSON
    (standard library only). The payload starts with a `text` field: one
    short line per hub, rounded scores, friendly dates ("Thu, Nov 26"),
    "before" only when the driver changed, and each score with a level in
    words ("Moderate (52) -> Severe (100)"; bands in `RISK_LEVELS`), with
    an emoji per level (🟢 🟡 🟠 🔴) and per hazard (❄️ 🌧️ 💨 🔥 🥶) so
    the message reads at a glance. Emoji are plain Unicode, so any receiver
    shows them; the JSON fields stay emoji-free for programs. People
    read it, and Slack incoming webhooks display it as the message; the
    full data follows for programs. A rejected delivery reports the
    receiver's reply (e.g. Slack's `invalid_payload`). If
    `ALERT_CHANNEL_URL` is set, the text ends with a "Discuss in the team
    channel" link, so whoever receives the alert (e.g. in a direct
    message) can take it to the team's channel in one click. It uses
    Slack's `<url|label>` link format; other receivers show it raw. The
    chat page shows the same link as a round Slack-logo button in the
    header (hover label "Team's Slack"). The page gets the link
    from `GET /team-channel`, which returns it only if it starts with
    `https://` (so a bad setting can't become a `javascript:` link); with
    no link the button stays hidden. A failed
    delivery doesn't fail the check: the alerts are already saved.
  - *No caching:* `fetch_json(..., use_cache=False)` always downloads the
    forecast; the permanent cache would freeze it.
  - *Agent tool:* `get_forecast_risk` lets the agent answer "what's the risk
    at Chicago this week?". It returns the score, each hazard's worst day
    (absolute, relative, percentile), the info notes, the daily forecast
    values and the scales. The prompt keeps it apart
    from the long-term score and tells Claude to say it can change.
- **Ranking entries name their category** (`overall`, `winter`, ...), so a
  comparison across hazards (e.g. Miami vs Houston on hurricane and flood)
  is unambiguous.
- **Tools return breakdowns, not just scores**, so Claude can explain *why*
  (e.g. "Detroit's ice storms are more frequent than in 98% of counties").

## Deployment
- **Live:** https://weather-risk-agent-sz0f.onrender.com
- **Render, free web service**, defined in `render.yaml` (in the repo, so
  the setup can be read and reviewed). It deploys from GitHub on every
  push to `main`.
- **Build:** `pip install -r requirements.txt && python -m app.scoring`.
  The second command fills the data cache (FEMA NRI + 5 years of weather
  per hub, ~2 minutes, ~5 MB) at build time, so the first question doesn't
  wait for downloads. Forecasts are never cached, so they stay live.
- **Start:** `uvicorn app.api:app --host 0.0.0.0 --port $PORT`; Render
  checks `/hubs` to know the app is up.
- **Secrets** are environment variables set in the Render dashboard
  (`ANTHROPIC_API_KEY`, `ALERT_WEBHOOK_URL`), never in git; Render
  generates `ALERT_TOKEN`.
- **Dependencies are pinned** in `requirements.txt` to the versions the
  tests pass with.
- **The chat is open**, without a password: it is a short-lived demo,
  Haiku costs ~$0.001 per question, and a monthly spend limit in the
  Anthropic console caps the damage if the URL leaks. A longer-lived
  deployment would add a login.
- **Free-plan trade-offs:** the server sleeps after ~15 minutes idle (the
  next request takes ~30-60 s), and its disk is wiped on every restart,
  so chat sessions and alert history reset (the data cache is rebuilt
  with the next deploy).

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
  scoring_config.py  all weights, scales and thresholds of both scores
  forecast.py   short-term risk score from the 7-day forecast
  alerts.py     risk-change check: compare, store, notify
  tools.py      the 5 tools Claude can call, and their definitions
  schemas.py    FinalAnswer: the JSON schema of the agent's answer
  agent.py      the Claude tool-use loop and system prompt
  api.py        FastAPI app: /, /chat, /hubs, /scores, /alerts
  static/index.html  the chat page (HTML + CSS + plain JavaScript)
  env.py        loads .env (API key)
data/
  hubs.json     the list of hubs (one line per hub)
  cache.db      SQLite cache, created on first use (not in git)
  history.db    alert history: every short-term score + alerts (not in git)
evals/
  cases.json    the 25 eval cases
  checks.py     deterministic checks run on each answer
scripts/
  test.py       runs unit tests or the smoke check
  chat.py       command-line chat with the agent (manual testing)
  eval.py       runs the eval set against the real agent
  demo_alerts.py  alert demo: baseline, in-memory scale change, re-check
render.yaml     Render deployment blueprint
tests/        unit tests (external APIs and Claude are mocked)
docs/ai-session/  the full conversation with the AI agent (plan + build)
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
- **Open-Meteo Forecast API.** No API key. The same daily variables for the
  next 7 days, for the short-term score only.

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

## Evaluation
`python scripts/eval.py` runs 25 cases (`evals/cases.json`) against the real
agent and checks each answer with deterministic code (`evals/checks.py`), no
LLM judge, so a failure always has a concrete reason.

- **Expected values come from our code at eval time** (e.g. the expected
  Midwest winter ranking is `rank_hubs("winter", "Midwest")`), not
  hard-coded, so the eval stays correct when the data is refreshed.
- **Every case also runs three default checks:** each ranking entry is a
  real hub and its score equals our code's; every number in the answer
  appears in a tool output, the system prompt or the question; and any ratio
  wording ("2.6 times", "twice") exactly matches a ratio a tool returned
  ("40% more" always fails: no tool returns percent changes).
- **Case types:** the 4 assignment questions, rankings by region/category,
  single-number questions, multi-turn follow-ups, two "this week" forecast
  questions (must call `get_forecast_risk`, no long-term ranking), and
  traps: an unknown hub, a year without data, and questions that tempt the
  model to calculate a difference or a ratio.
- **`--repeat N`** runs each case N times: answers vary between runs, so a
  pass rate says more than one pass.
- **What the eval changed:** it found the model counting items ("the 21
  hubs"), summarizing with its own round thresholds ("all above 85"),
  subtracting scores ("2.9 points"), computing ratios ("twice as
  frequent"), working out years, and once answering a follow-up with a plan
  instead of data. Each fix went into the tools or the code (see "Claude
  decides, code computes" and "Completeness flag"), not only the prompt.
- **Cost and time** are printed per run (`--repeat 3` on Haiku: ~$0.10, ~2
  minutes), so a model or effort change can be judged on quality, cost and
  speed together.
- **Model choice:** the Opus vs Haiku comparison (every case 3 times on
  each) is under "Model" in the architecture section.
- **Latest results:** Haiku (default), every case 3 times: 72/72 runs,
  444/444 checks, $0.11, 6 s median per question; 4 incomplete answers
  (all follow-ups) were caught and retried successfully. Opus on the cases
  it used to fail (ratio, difference, comparisons), 3 times each: 12/12.
  After adding the forecast tool (25 cases, once each): 25/25 runs,
  156/156 checks, $0.04.

## Data storage choice
**SQLite**, from the Python standard library, in two files, no server to
run:
- `data/cache.db`: API responses cached by request URL, so each request is
  sent once: faster answers, fewer API calls, and the demo keeps working if
  an API is slow. Forecasts are never cached.
- `data/history.db`: the alert history (every hub's short-term score at
  every check, and every alert raised). A separate file on purpose: deleting `cache.db`
  to refresh NRI data must not wipe the history.

JSON files would work too, but SQLite handles "read the last scores, write
the new ones and the alerts" in one transaction. Postgres would be overkill
for one process and a few MB of data. Chat history is kept in memory (see
Limitations).

## Scope
In scope: the four kinds of question in the assignment (rank, compare,
single weather number, explain a score) for 21 hubs, with follow-ups, through
a chat page and an API. Plus the bonus risk-change alert, on a short-term
score from the 7-day forecast (not on the long-term score, which barely
moves; why, and why there is no scheduled scan: "Short-term risk score and
alert" above), which the agent can also quote for "this
week" questions.

Out of scope, on purpose:
- **Forecasts in the long-term score.** Investment decisions are about
  long-term exposure, so the main score uses 5 years of history only. The
  forecast feeds only the separate short-term score.
- **Cost of disruption** (revenue, shipments per hub): we have no such data,
  so the score measures exposure, not financial impact.

## Uncertainty
- Every answer carries a `confidence` (`high` / `medium` / `low`): high when
  the tools answer the question directly, medium when the question had to be
  interpreted, low when the data only partly covers it. The chat page shows
  it as a neutral label ("Confidence: high").
- Every answer lists its `assumptions` (e.g. "last year = 2025", "Denver =
  the hub's coordinates"), so the analyst sees what the number depends on.
- The score itself is not a probability: it ranks exposure on a 0-100 scale.
  Small gaps (a few points) between hubs are within the uncertainty of the
  data and the scale choices below, and should not decide an investment on
  their own.

## Assumptions
- Hubs are fictional, located in real US cities.
- Regions follow the US Census Bureau definition (Northeast, Midwest, South, West).
- A hub's hazard exposure is how often each hazard happens in its county (NRI frequency).
- Weather is taken at the hub's coordinates (Open-Meteo grid, ~10 km).

## Limitations
- The eval's text checks (`mentions`) match phrases, so a correct answer in
  unexpected words can fail; failed cases are worth reading before acting.
- The "no invented numbers" check allows small whole numbers (0-10) and
  rounding, so it can't catch every possible slip.
- Haiku follows instructions a little less reliably than Opus; the eval and
  the completeness retry cover the failures seen so far. Switch with
  `AGENT_MODEL=claude-opus-5-5` if quality matters more than cost.
- Conversation history lives in memory: it is lost when the server
  restarts, sessions never expire, and it works for one server process only.
  Two requests in the same session at the same moment are not guarded.
- The agent answers only from our hubs and our tools (NRI, Open-Meteo
  history and the 7-day forecast); it cannot search the web or other sources.
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
- A drift slower than 10 points in 3 days never alerts (by design: it is
  not sudden). The window and thresholds are judgment calls in the config.
- Changing a forecast scale changes every hub's score, so the next check
  alerts on many hubs although the weather didn't change ("before" and
  "now" then show the same value). Clearing `data/history.db` after a scale
  change avoids it; storing a fingerprint of the scales would automate it.
- The score history grows by 21 rows per check and is never pruned (about
  30,000 rows a year at 4 checks a day: no problem for SQLite).
- The short-term scales (e.g. 15 cm of snow in a day = 100) are judgment
  calls, like the long-term ones, and they ignore how a hazard combines with
  others (e.g. snow plus strong wind). Forecast values for days 5-7 are much
  less reliable than for days 1-2.
- "Normal" comes from only 5 years (~150 days per calendar month), so the
  far tail is thin: "beyond the 99th percentile" rests on one or two past
  days. The history (reanalysis) and the forecast come from different
  weather models, which can shift percentiles a little. Calendar months
  are a coarse season: late November is compared with early November too.
- A check calls the forecast API once per hub (21 calls, ~5 s); fine at this
  size, but many hubs would need Open-Meteo's multi-location requests.
- The cache never expires. That is fine for historical data, but NRI updates
  about once a year: delete `data/cache.db` to refresh.
