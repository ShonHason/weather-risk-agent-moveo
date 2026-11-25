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

## Add a hub

Add one line to `data/hubs.json` with `id`, `name`, `city`, `state`, `lat`,
`lon` and `county_fips`. The region is derived from the state automatically.
Run `python scripts/test.py` to check the file is valid.
