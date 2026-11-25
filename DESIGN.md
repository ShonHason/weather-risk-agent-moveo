# Design

Work in progress. Filled in as the steps are built. See PLAN.md for the agreed decisions.

## System architecture
TBD

## Repository structure

```
app/            application code
  hubs.py       loads data/hubs.json and adds each hub's region
  fetch.py      downloads JSON from public APIs, through the cache
  cache.py      SQLite key-value cache for API responses
  nri.py        FEMA National Risk Index client (hazard scores per county)
  weather.py    Open-Meteo client (daily weather history)
data/
  hubs.json     the list of hubs (one line per hub)
  cache.db      SQLite cache, created on first use (not in git)
scripts/
  test.py     runs unit tests or the smoke check
tests/        unit tests
```

## Data sources
- **FEMA National Risk Index (NRI), December 2025 version.** Official FEMA
  ArcGIS service "National Risk Index Counties", no API key. Gives a 0-100
  national percentile risk score per hazard for each county. Hazards that do
  not apply to a county (e.g. hurricane in Denver) are "Not Applicable".
- **Open-Meteo Historical Weather API.** No API key. Daily snowfall,
  precipitation, min/max temperature and max wind gusts for the last 5 full
  calendar years at each hub's coordinates.

## Data storage choice
**SQLite**, from the Python standard library. One file (`data/cache.db`), no
server to run. API responses are cached by request URL, so each request is
sent once: faster answers, fewer API calls, and the demo keeps working if an
API is slow. JSON files would work too, but SQLite also fits the planned score
history. Postgres would be overkill for one process and a few MB of data.

## Assumptions
- Hubs are fictional, located in real US cities.
- Regions follow the US Census Bureau definition (Northeast, Midwest, South, West).
- A hub's hazard exposure is its county's NRI score.
- Weather is taken at the hub's coordinates (Open-Meteo grid, ~10 km).

## Limitations
- The cache never expires. That is fine for historical data, but NRI updates
  about once a year: delete `data/cache.db` to refresh.
- NRI risk scores include the value of exposed buildings and population, so
  large urban counties tend to score high.
