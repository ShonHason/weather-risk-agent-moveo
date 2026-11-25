# Weather Risk Intelligence Agent

An AI agent that helps analysts decide which distribution hubs are most exposed
to severe weather. Work in progress.

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

## Run the tests

```bash
python scripts/test.py           # unit tests (mocked, fast, free)
python scripts/test.py smoke     # one real API call
```

## Run the eval set

```bash
python scripts/eval.py                # 24 cases against the real agent (~$0.04 on Haiku)
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
then a follow-up like "And in the South?".

## Run the app (chat page + API)

```bash
uvicorn app.api:app              # chat page: http://127.0.0.1:8000
```

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

## Add a hub

Add one line to `data/hubs.json` with `id`, `name`, `city`, `state`, `lat`,
`lon` and `county_fips`. The region is derived from the state automatically.
Run `python scripts/test.py` to check the file is valid.
