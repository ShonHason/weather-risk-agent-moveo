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

## Run the tests

```bash
python scripts/test.py           # unit tests (mocked, fast, free)
python scripts/test.py smoke     # one real API call
```

## Chat with the agent

```bash
python scripts/chat.py           # needs ANTHROPIC_API_KEY in .env
python scripts/chat.py --json    # also prints the raw structured answer
```

Try: "Which hubs in the Midwest are most exposed to winter disruption?",
then a follow-up like "And in the South?".

## Run the API

```bash
uvicorn app.api:app --reload     # interactive docs: http://127.0.0.1:8000/docs
```

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
