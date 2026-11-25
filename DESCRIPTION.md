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
as a web chat page on top of an API.

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
   our tools (list, rank, compare, get metrics), and writes the answer. It
   never computes a number: every score, gap, average and ratio it quotes
   comes from the tools.
4. **Structured answers.** Claude must reply in a fixed JSON format (answer,
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
- 76 unit tests for the scoring, tools, API and agent loop (external
  services mocked).
- An evaluation set of 24 questions, including traps (an unknown hub, a
  forecast request, invitations to calculate). Answers are checked by code,
  not by another model: correct hubs and scores, no invented numbers. Latest
  run: 72 of 72 runs passed (each question 3 times).

## Limits and scope
- It measures exposure to weather, not financial impact: we have no data on
  each hub's revenue or volume.
- Long-term history only, no forecasts.
- Some scale choices (e.g. 40 snow days a year = maximum) are judgment calls,
  and small score differences between hubs should not decide an investment
  on their own.
- Chat memory is kept in the server's memory and lost on restart.
- Not yet built: the bonus risk-change alert, voice, and a public URL.
