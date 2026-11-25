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
  nri.py        FEMA National Risk Index client (hazard frequency per county)
  weather.py    Open-Meteo client (daily weather history)
  metrics.py    daily weather -> metrics (snow days, hot days, ...) per hub
  scoring.py    the deterministic risk score, breakdown and ranking
  scoring_config.py  all weights, scales and thresholds of the score
data/
  hubs.json     the list of hubs (one line per hub)
  cache.db      SQLite cache, created on first use (not in git)
scripts/
  test.py     runs unit tests or the smoke check
tests/        unit tests
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

## Data storage choice
**SQLite**, from the Python standard library. One file (`data/cache.db`), no
server to run. API responses are cached by request URL, so each request is
sent once: faster answers, fewer API calls, and the demo keeps working if an
API is slow. JSON files would work too, but SQLite also fits the planned score
history. Postgres would be overkill for one process and a few MB of data.

## Assumptions
- Hubs are fictional, located in real US cities.
- Regions follow the US Census Bureau definition (Northeast, Midwest, South, West).
- A hub's hazard exposure is how often each hazard happens in its county (NRI frequency).
- Weather is taken at the hub's coordinates (Open-Meteo grid, ~10 km).

## Limitations
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
- The cache never expires. That is fine for historical data, but NRI updates
  about once a year: delete `data/cache.db` to refresh.
