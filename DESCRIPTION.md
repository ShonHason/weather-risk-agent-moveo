# Weather Risk Intelligence Agent: overview

## The problem
A logistics company runs distribution hubs across the US. Severe weather
shuts hubs down, and each year the company picks a few hubs for resilience
upgrades. Analysts need to know which hubs are most exposed, and why.

## What we built
A chat assistant that answers questions like "Which Midwest hubs are most
exposed to winter disruption?" or "Why is the Dallas hub's risk high?" for 21
fictional hubs in real US cities. It ranks and compares hubs, answers single
weather questions ("What percentage of days in Denver last year had
snowfall?"), explains its reasoning and handles follow-up questions. It runs
as a web chat page on top of an API, typed or by voice (spoken questions
get a spoken answer). A second, short-term score from the
7-day forecast powers risk-change alerts for the operations team, and lets
the agent answer "what's the risk at Chicago this week?".

## How it works
1. **Public data.** FEMA's National Risk Index gives how often each hazard
   (winter storms, ice, heat, floods, hurricanes, tornadoes, hail, wind)
   happens in each hub's county. Open-Meteo gives 5 years (2021-2025) of
   observed daily weather at each hub. Both are free, and responses are
   cached in a local SQLite file.
2. **A deterministic risk score.** Python code turns the data into a 0-100
   score per hub in five categories (winter, heat, flood, hurricane, severe
   storm) and an overall score. Every weight and scale is in one config file,
   so the score can be checked by hand and gives the same result every time.
3. **Claude as the analyst's interface.** Claude reads the question, calls
   our tools (list, rank, compare, get metrics, forecast), and writes the answer. It
   never computes a number: every score, gap, average and ratio it quotes
   comes from the tools.
4. **Risk-change alerts.** A protected webhook (`POST /alerts/check`),
   called by any scheduler or by hand, scores every hub's coming week (snow, heavy
   rain, wind, heat, extreme cold), both on a fixed scale and against what
   is normal for that hub in that month (-8 °C matters in Dallas, not in
   Minneapolis), compares with its scores of the last 3
   days, and alerts on a move of 10 points or more (so gradual rises count
   too), naming what drove the change. Alerts are saved and can be pushed
   to a chat channel's webhook.
5. **Structured answers.** Claude must reply in a fixed JSON format (answer,
   ranking, reasoning, assumptions, confidence), checked by our code before
   it reaches the user.

## Key choices
- **Code computes, the model explains.** Numbers that drive investment
  decisions must be reproducible and traceable, so they never come from the
  language model.
- **Frequency, not FEMA's overall risk score.** FEMA's score is driven by
  population and property value, so big cities score high on everything. A
  hub is one site; what matters is how often it is disrupted.
- **Claude Haiku by default.** Our evaluation showed it as accurate as the
  largest model here, about 46 times cheaper and twice as fast.

## How we know it works
- 113 unit tests for the scoring, alerts, tools, API and agent loop
  (external services mocked).
- An evaluation set of 25 questions, including traps (an unknown hub, a
  year without data, invitations to calculate) and "this week" forecast
  questions. Answers are checked by code, not by another model: correct
  hubs and scores, no invented numbers. All 25 pass; before the forecast
  tool, the 24 earlier ones passed 72 of 72 runs on Haiku (each question
  3 times), and Opus passed the ratio and gap cases 12 of 12; Haiku was
  chosen at about 1/46 of the cost.

## Limits and scope
- It measures exposure to weather, not financial impact: we have no data on
  each hub's revenue or volume.
- The investment score uses long-term history only; the forecast is used
  only for the short-term score and alerts, and forecasts can change.
- Some scale choices (e.g. 40 snow days a year = maximum) are judgment calls,
  and small score differences between hubs should not decide an investment
  on their own.
- Chat memory is kept in the server's memory and lost on restart.
- Alerts need an external scheduler to call the webhook (e.g. cron).
- Live at https://weather-risk-agent-sz0f.onrender.com (free hosting: it
  sleeps when idle, and the alert history resets on restart). Not built:
  a scheduled weather scan on the hosted app.
- Voice uses the browser's speech service: Chrome, Edge and Safari (not
  Firefox), English only.
