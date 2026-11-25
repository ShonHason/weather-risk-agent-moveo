# Weather Risk Intelligence Agent: overview

## The problem
A logistics company runs distribution hubs across the US. Severe weather
shuts hubs down, and each year the company picks a few hubs for resilience
upgrades. Analysts need to know which hubs are most exposed, and why.

## What we built
A chat assistant for 21 fictional hubs in real US cities. It ranks and
compares hubs ("Which Midwest hubs are most exposed to winter disruption?"),
answers weather questions ("What percentage of days in Denver last year had
snowfall?"), explains its reasoning and handles follow-ups. It runs as a web
chat page on top of an API, typed or by voice. A bonus short-term score from
the 7-day forecast powers risk-change alerts.

## How it works
1. **Public data.** FEMA's National Risk Index gives how often each hazard
   happens in each hub's county; Open-Meteo gives 5 years of observed daily
   weather at each hub. Responses are cached in SQLite.
2. **A deterministic risk score.** Python code turns the data into a 0-100
   score in five categories (winter, heat, flood, hurricane, severe storm)
   plus an overall score. All weights live in one config file.
3. **Claude as the interface.** Claude reads the question, calls our tools
   (list, rank, compare, metrics, forecast) and writes the answer. It never
   computes a number: every score, gap and ratio comes from the tools.
4. **Structured answers.** Claude must reply in a fixed JSON schema (answer,
   ranking, reasoning, assumptions, confidence), validated in code.
5. **Risk-change alerts.** A protected webhook scores every hub's coming
   week and alerts, optionally to Slack, when a hub's score moves 10 points
   or more.

## Key choices
- **Code computes, the model explains.** Numbers behind investment decisions
  must be reproducible, so they never come from the language model.
- **Hazard frequency, not FEMA's overall risk score.** FEMA's score grows
  with population and property value, so big cities score high on
  everything. For one site, what matters is how often it is disrupted.
- **Claude Haiku by default.** In our evaluation it matched Opus at about
  1/46 of the cost and twice the speed.

## How we know it works
- 113 unit tests, with external services mocked.
- 25 evaluation questions, including traps (an unknown hub, a year without
  data, invitations to calculate), checked by code rather than by another
  model. All pass.

## Limits and scope
- It measures exposure to weather, not financial impact (no revenue data).
- Some scale choices are judgment calls; small score gaps between hubs
  should not decide an investment on their own.
- Chat memory is in server memory; the free hosting sleeps when idle and
  resets the alert history on restart. Alerts need an external scheduler.
- Voice works in Chrome, Edge and Safari, in English.
