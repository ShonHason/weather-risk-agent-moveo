# Session 5 (started 2026-11-25 20:13 UTC)

### User

Audit this repository against the assignment requirements below.
For EACH item, report: ✅ Done / ⚠️ Partial / ❌ Missing, with evidence
(file path + line or a short explanation). Do not change any code yet.

FUNCTIONAL
1. Uses public APIs to gather weather and hazard data
2. Ranks or compares hubs based on a defined logic/KPI
3. Explains its reasoning clearly
4. Supports conversational follow-up questions
5. Can answer these example questions correctly:
   - Which hubs in the Midwest are most exposed to winter disruption?
   - Compare Miami and Houston in terms of hurricane and flood exposure.
   - What percentage of days in Denver last year had snowfall?
   - Why is the Dallas hub's weather disruption risk high?

TECHNICAL REQUIREMENTS
6. Deterministic scoring/ranking logic in code (not only LLM output)
7. Chat interface (voice = bonus)
8. Agent exposed through an API that the chat UI uses
9. Enforced structured output (JSON schema) between the LLM and the code
10. Small evaluation set + a way to run it
11. Assumptions, uncertainty and scoping clearly communicated
    (in docs AND in the agent's answers)
12. Bonus: scheduled or webhook-triggered alert when a hub's risk score changes

DELIVERABLES
13. Source code with clear run instructions (README) that work from a fresh clone
14. .env.example, no secrets committed
15. Deployed URL works (bonus)
16. Short design/architecture doc covering:
    a. System architecture: components and how they communicate
    b. Repository structure
    c. Data storage choice and why
17. Full AI agent session (plan + conversation) included in the repo

Then:
- Run the eval set and report the results.
- List the top 5 gaps ordered by impact on the interview, with a suggested fix
  and estimated time for each.
- List 5 questions an interviewer is likely to ask about this design.

### Claude

I'll audit the repo read-only: structure first, then the key files, then run the eval set.

<details><summary>Tool calls (1)</summary>

- `Bash` List tracked files, sizes, gitignore

</details>

### Claude

Notably, no session transcript is tracked. Reading the core code and docs now.

<details><summary>Tool calls (4)</summary>

- `Bash` Read agent, schemas, scoring, API
- `Bash` Read tools, hubs, metrics, data clients
- `Bash` Read README, env example, deploy config, plan
- `Bash` Design doc headings, session refs, eval cases

</details>

### Claude

Now running the unit tests, the eval set (real API, about $0.04 on Haiku), and a check on the deployed URL.

<details><summary>Tool calls (3)</summary>

- `Bash` Run unit test suite
- `Bash` Run eval set against real agent
- `Bash` Check deployed URL endpoints and live chat

</details>

### Claude

All checks pass. Last, I'm confirming the chat page shows assumptions and confidence, and checking the uncertainty section in DESIGN.md.

<details><summary>Tool calls (1)</summary>

- `Bash` Check UI fields and DESIGN sections

</details>

### Claude

Last check: running tests from a fresh clone, and seeing whether DESIGN.md records multi-run eval pass rates.

<details><summary>Tool calls (1)</summary>

- `Bash` Fresh clone, install, run tests; grep eval results

</details>

### Claude

# Audit: weather-risk-agent vs. the assignment

I changed no code. 16 of the 17 items are done or mostly done. One mandatory deliverable is missing: the AI agent session transcript is not in the repo.

## Functional

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Public APIs | ✅ | FEMA NRI ArcGIS service ([app/nri.py:20](app/nri.py#L20)), Open-Meteo archive ([app/weather.py:11](app/weather.py#L11)) and Open-Meteo forecast ([app/forecast.py:29](app/forecast.py#L29)). None of them need a key. |
| 2 | Ranking with a defined KPI | ✅ | Five categories, equal 20% weights. Winter, heat and flood are 70% NRI percentile + 30% observed weather; hurricane and severe storm are NRI only ([app/scoring.py:45-84](app/scoring.py#L45-L84), [app/scoring_config.py](app/scoring_config.py)). |
| 3 | Explains its reasoning | ✅ | `reasoning` is a required field ([app/schemas.py:32](app/schemas.py#L32)). Tools return the breakdown behind each score (worst hazard, NRI and observed parts). The UI shows it ([index.html:278](app/static/index.html#L278)). |
| 4 | Follow-up questions | ✅ | One `Agent` per `session_id` keeps the history ([app/api.py:39,62-66](app/api.py#L39)). The eval has 3 follow-up cases. |
| 5 | The four example questions | ✅ | All 4 `assignment_*` cases pass. I also asked the live deploy the Denver question: "37 days, 10.1% of 2025". |

## Technical requirements

| # | Item | Status | Evidence |
|---|---|---|---|
| 6 | Scoring is deterministic code | ✅ | The scoring is pure Python. The system prompt forbids the model from calculating numbers ([app/agent.py:41-52](app/agent.py#L41-L52)), and tools hand it pre-computed gaps and ratios ([app/tools.py:157-216](app/tools.py#L157-L216)). |
| 7 | Chat interface (voice bonus) | ⚠️ | The chat page and CLI chat both exist. Voice is not built and is listed as out of scope in [DESIGN.md:385](DESIGN.md#L385). |
| 8 | API used by the chat UI | ✅ | The page calls `POST /chat` with a `session_id` ([index.html:309](app/static/index.html#L309)). |
| 9 | Enforced JSON schema | ✅ | The Pydantic schema is sent as `output_config.format` ([app/agent.py:111,154](app/agent.py#L111)). The reply is validated again with `extra="forbid"` ([app/agent.py:203-209](app/agent.py#L203-L209)). |
| 10 | Eval set + runner | ✅ | 25 cases ([evals/cases.json](evals/cases.json)) with deterministic checks ([evals/checks.py](evals/checks.py)). Run with `python scripts/eval.py`, plus `--repeat` and `--case`. |
| 11 | Assumptions and uncertainty, in docs and answers | ✅ | Every answer has `assumptions` and `confidence`, and the UI shows both. DESIGN.md has Scope, Uncertainty, Assumptions and Limitations sections. Two DESIGN.md statements are out of date (gap 2). |
| 12 | Bonus: alert on risk change | ✅/⚠️ | `POST /alerts/check` is a token-protected webhook. Alerts can go to a Slack webhook. You decided not to add a scheduler ([PLAN.md:31](PLAN.md#L31)). The alert watches the 7-day forecast score, not the main long-term score. |

## Deliverables

| # | Item | Status | Evidence |
|---|---|---|---|
| 13 | README works from a fresh clone | ✅ | I cloned into the scratchpad, installed requirements and ran the unit tests: 113 passed. That ran on Python 3.11, although the README says 3.12+. |
| 14 | `.env.example`, no secrets | ✅ | `.env` is in [.gitignore](.gitignore). [.env.example](.env.example) has empty or commented values, and Render secrets use `sync: false`. |
| 15 | Deployed URL (bonus) | ✅ | On the live Render URL, `/hubs`, `/scores` and `/` return 200, and a real `/chat` call returned a correct answer. |
| 16a | Architecture | ✅ | Diagram and component descriptions ([DESIGN.md:6](DESIGN.md#L6)). |
| 16b | Repo structure | ✅ | [DESIGN.md:241](DESIGN.md#L241) |
| 16c | Storage choice and why | ✅ | SQLite in two files, with the reasons and alternatives ([DESIGN.md:360](DESIGN.md#L360)). |
| 17 | Full AI agent session in the repo | ❌ | No transcript is tracked. [PLAN.md:62](PLAN.md#L62) has a reminder to add it. There are 5 local session `.jsonl` files under `~/.claude/projects/`. |

## Eval results (just run, Haiku, effort medium)
- **Runs:** 25/25 passed, and 156/156 checks passed.
- **Cost:** $0.04 in total, about $0.001 per case.
- **Time:** 6 s median per case, 12 s for the slowest, 39 s for the whole set.
- **Retries:** 0.
- **Unit tests:** 113 passed.

This was one run per case. DESIGN.md explains that `--repeat` gives more reliable pass rates.

## Top 5 gaps, by impact on the interview

1. **Session transcript missing (#17, mandatory).** Export the sessions with `/export`, or convert the local `.jsonl` files to Markdown under `docs/ai-session/`, and link them from the README. Check them for secrets first. **About 30 min.**
2. **DESIGN.md contradicts the code in two places.**
   - [DESIGN.md:384](DESIGN.md#L384) says deployment is out of scope, but the app is deployed.
   - [DESIGN.md:420](DESIGN.md#L420) says the agent "cannot fetch forecasts", but it has `get_forecast_risk`.
   - Minor: [PLAN.md:48](PLAN.md#L48) says 24 eval cases; there are 25.

   An interviewer who reads the docs will notice. **About 10 min.**
3. **The alert watches the forecast score, not the main risk score, and nothing schedules it.** Expect a challenge on this. Add one clear paragraph to DESIGN.md: the long-term score only changes when the data changes (about yearly), so a short-term score is the meaningful thing to watch, and scheduling needs persistent storage. Optionally add a GitHub Actions cron that calls the endpoint. **10 min for the doc; 30 min with the cron.**
4. **Eval evidence is a single run.** Run `--repeat 3` once, and record per-case pass rates and the Haiku-vs-Opus comparison in DESIGN.md's Evaluation section. That backs up "chosen by eval" with numbers. **About 15 min, about $0.15.**
5. **The voice bonus is not built.** A microphone button using the browser's Web Speech API would need no new dependencies and only change [index.html](app/static/index.html). It needs your approval as a new feature. **45–60 min.** If you skip it, mention instead that the public `/chat` has no rate limit and that sessions never expire.

## 5 questions an interviewer will likely ask
1. Why is the score 70/30 NRI vs. observed weather, why equal category weights, and why the worst hazard rather than an average? How sensitive is the ranking to those choices?
2. How do you make sure the LLM never invents or miscalculates a number? What happens when it breaks that rule, and how does the eval catch it?
3. Why build a raw tool-use loop instead of an agent framework? Why Haiku over Opus? What did the eval show?
4. How would this scale to 2,000 hubs and many users? Consider in-memory sessions, a single process, the SQLite cache that never expires, and one forecast call per hub.
5. NRI frequency is county-level and ignores severity (for example, King County includes the Cascades). How does that bias the results, and what would you add to fix it?

I can start on gaps 1 and 2 first; tell me which ones you want.

### User

start with gaps 1 and 2

### Claude

Plan: for gap 1, convert the local session logs to readable Markdown in `docs/ai-session/`, removing tool noise and redacting secrets, then link it from the README. For gap 2, fix the three outdated doc lines. First, a look at the session files:

<details><summary>Tool calls (3)</summary>

- `Bash` Inspect local session log files
- `Write` /private/tmp/claude-501/-Users-shonhason-AIprojects-weather-risk-agent-moveo/09e8c9e5-b341-4fdc-894b-0d7565f9b558/scratchpad/export_sessions.py
- `Bash` Generate transcripts and scan for secrets

</details>

### Claude

The only `sk-ant-` hit is the placeholder `sk-ant-...`. Next I'm checking the 7 redactions in session 3 and looking for other private links, such as Slack channel IDs or webhook.site URLs:

<details><summary>Tool calls (2)</summary>

- `Bash` Check redaction contexts and private links
- `Bash` View Slack workspace mentions and redactions

</details>

### Claude

No real webhook was exposed: the redacted URLs were placeholders. But the regex swallowed their closing backticks, and the Slack workspace subdomain is private-ish. I'll fix both and regenerate:

<details><summary>Tool calls (1)</summary>

- `Bash` Tighten redaction and regenerate transcripts

</details>
