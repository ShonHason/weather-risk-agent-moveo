# Weather Risk Intelligence Agent

An AI agent that helps analysts decide which of 21 (fictional) US distribution
hubs are most exposed to severe weather. It ranks hubs with a deterministic
risk score built from public data (FEMA National Risk Index + Open-Meteo
weather history), and Claude explains the results in a chat.

**Live demo:** https://weather-risk-agent-sz0f.onrender.com (free plan:
the first request after ~15 minutes idle takes ~30-60 s to wake it up).
API docs: https://weather-risk-agent-sz0f.onrender.com/docs

- How it works and why: [DESIGN.md](DESIGN.md)
- One-page summary: [DESCRIPTION.md](DESCRIPTION.md)
- The full AI agent session (plan + build): [docs/ai-session/](docs/ai-session/README.md)

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # add your ANTHROPIC_API_KEY
uvicorn app.api:app              # open http://127.0.0.1:8000
```

Try the assignment's questions:

- Which hubs in the Midwest are most exposed to winter disruption?
- Compare Miami and Houston in terms of hurricane and flood exposure.
- What percentage of days in Denver last year had snowfall?
- Why is the Dallas hub's weather disruption risk high?

The first question after a fresh install downloads the data (~1-2 min);
after that it is cached in `data/cache.db`.

## Setup

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then add your ANTHROPIC_API_KEY
```

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Claude API key |
| `AGENT_MODEL` | `claude-haiku-5-5` | or `claude-opus-5-5` (slower, ~46x pricier, see DESIGN.md) |
| `AGENT_EFFORT` | `medium` | `low`, `medium` or `high` reasoning effort |
| `ALERT_TOKEN` | (unset = alerts off) | secret for `POST /alerts/check` |
| `ALERT_WEBHOOK_URL` | (unset) | where new alerts are POSTed as JSON |
| `ALERT_CHANNEL_URL` | (unset) | Slack channel linked at the end of each alert and from the chat page's Slack button |

## Run the tests

```bash
python scripts/test.py           # unit tests (mocked, fast, free)
python scripts/test.py smoke     # one real API call
```

## Run the eval set

```bash
python scripts/eval.py                # 25 cases against the real agent (~$0.04 on Haiku)
python scripts/eval.py --repeat 3     # each case 3 times: pass rates
python scripts/eval.py --case trap_ratio
AGENT_MODEL=claude-opus-5-5 python scripts/eval.py    # compare another model
```

Prints pass/fail, cost and response times; details are saved to
`evals/last_run_<model>_<effort>_<full|partial>.json`.

## Chat with the agent

```bash
python scripts/chat.py           # needs ANTHROPIC_API_KEY in .env
python scripts/chat.py --json    # also prints the raw structured answer
```

Try: "Which hubs in the Midwest are most exposed to winter disruption?",
then a follow-up like "And in the South?". For the coming week: "What's the
risk at the Chicago hub this week?" (uses the 7-day forecast).

## Run the app (chat page + API)

```bash
uvicorn app.api:app              # chat page: http://127.0.0.1:8000
```

**Voice:** click the 🎤 button next to Send (Chrome, Edge or Safari; allow
the microphone once), ask your question, and pause. After 2 s of silence a
3-second "Sending in 3…" countdown starts: type or click 🎤 to cancel and
fix the text, or press Enter to send now. The short answer is read aloud
(click ⏹, where the mic was, or press Esc to stop it); typed questions stay
silent. Not available in Firefox (the button is
hidden). For a more natural voice on a Mac, download a Premium English
voice (System Settings → Accessibility → Spoken Content → System voice →
Manage Voices); in Edge, the "Natural" voices are used automatically.

Add `--reload` while developing (it clears chat sessions on every code change).

Activate the virtualenv first (`source .venv/bin/activate`). Otherwise a
globally installed `uvicorn` may run instead and fail with
`No module named 'anthropic'`. Without activating: `.venv/bin/uvicorn app.api:app`.

## Use the API directly

Interactive docs: http://127.0.0.1:8000/docs

```bash
curl "localhost:8000/scores?category=winter&region=Midwest"
curl -X POST localhost:8000/chat -H 'content-type: application/json' \
     -d '{"message": "Why is the Dallas hub risk high?"}'
# follow-up: send the session_id from the reply
```

## See the risk scores

```bash
python -m app.scoring            # ranks all hubs (first run downloads data, ~1-2 min)
```

The weights and scales behind the score are in `app/scoring_config.py`.

```bash
python -m app.forecast           # short-term (7-day forecast) score per hub, live
```

## Risk-change alerts

A second, short-term score per hub comes from the 7-day forecast. It
counts both how severe the weather is (a fixed scale) and how unusual it is
for that hub in that month (-8 °C matters in Dallas, not in Minneapolis);
unusual days that aren't disruptive are listed as info notes. A check
recomputes it for every hub and raises an alert when a hub's score is 10
points or more away from any of its scores in the last 3 days (so a gradual
rise is caught too), and the old or new score is at least 40. After an
alert, the hub's older scores stop counting, so the same change doesn't
alert twice. The first check only saves a baseline. All these numbers are
in `app/scoring_config.py`.

Set `ALERT_TOKEN` in `.env`, start the server, then trigger a check:

```bash
curl -X POST localhost:8000/alerts/check -H "X-Alert-Token: $ALERT_TOKEN"
curl localhost:8000/alerts                 # the latest alerts
```

The app doesn't schedule checks itself; call the endpoint from any
scheduler. For example, every 6 hours with cron:

```
0 */6 * * * curl -s -X POST http://127.0.0.1:8000/alerts/check -H "X-Alert-Token: <token>"
```

If `ALERT_WEBHOOK_URL` is set, new alerts are also POSTed there as JSON.
The `text` field comes first: a short summary for people, which Slack shows
as the message. The full data follows:

```
{"text": "⚠️ Weather risk alert (7-day forecast): 2 hubs changed
- Seattle Hub: 📈 up 🟡 Moderate (52) -> 🔴 Severe (100), 💨 wind gusts 71 km/h on Thu, Nov 26
- Buffalo Hub: 📈 up 🔴 Severe (88) -> 🔴 Severe (100), 💨 wind gusts 84 km/h on Thu, Nov 26
  (before: 🌧️ rain 45 mm on Thu, Nov 26)",
 "checked_at": "...",
 "alerts": [{"hub_name", "old_score", "new_score", "change", "since",
             "now": {...}, "before": {...}, "notes": [...], "message"}, ...]}
```

Alerts are sorted biggest change first. Levels: 🟢 Low (0-29), 🟡 Moderate
(30-59), 🟠 High (60-79), 🔴 Severe (80-100); hazards: ❄️ snow, 🌧️ rain,
💨 wind, 🔥 heat, 🥶 cold; set in `RISK_LEVELS` in
`app/scoring_config.py`.

**Send alerts to Slack:** create an incoming webhook for a channel
(api.slack.com/apps -> Create New App -> From scratch -> Incoming Webhooks ->
On -> Add New Webhook -> pick the channel) and put its
`https://hooks.slack.com/services/...` URL in `ALERT_WEBHOOK_URL`. Slack
posts the `text` field as the message. To end each alert with a
"Discuss in the team channel" link, set `ALERT_CHANNEL_URL` to the
channel's link (right-click the channel -> Copy -> Copy link). Treat the URL as a secret: anyone
who has it can post to the channel. If a delivery fails, the check's
`webhook` field shows the receiver's reply (e.g. `failed: HTTP 400
invalid_payload`).

**Demo** (forecasts rarely move 10 points within minutes):

```bash
python scripts/demo_alerts.py
```

It runs a baseline check on the real forecast in a temporary history, makes
the wind scale stricter in memory only (no config file changes), runs a
second check, and sends the resulting alerts to `ALERT_WEBHOOK_URL`. The
real history (`data/history.db`) is not touched; delete that file to start
the real alerts over.

## Deploy to Render (free)

The repo has a blueprint, `render.yaml`. One-time setup:

1. Sign in at https://render.com with GitHub.
2. **New** -> **Blueprint** -> pick this repository -> **Apply**.
3. When asked, fill in `ANTHROPIC_API_KEY` and, optionally,
   `ALERT_WEBHOOK_URL`. Render generates `ALERT_TOKEN` (see it under the
   service's **Environment** tab).
4. The first build takes ~3-4 minutes (it downloads the data cache). The
   app is then at `https://<service-name>.onrender.com`.

Every push to `main` redeploys. On the free plan the app sleeps after ~15
minutes idle: open it a minute before a demo. Set a monthly spend limit in
the Anthropic console, since the chat is public.

## Add a hub

Add one line to `data/hubs.json` with `id`, `name`, `city`, `state`, `lat`,
`lon` and `county_fips`. The region is derived from the state automatically.
Run `python scripts/test.py` to check the file is valid.
