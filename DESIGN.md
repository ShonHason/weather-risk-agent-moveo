# Design

Work in progress. Filled in as the steps are built. See PLAN.md for the agreed decisions.

## System architecture
TBD

## Repository structure

```
app/          application code
  hubs.py     loads data/hubs.json and adds each hub's region
data/
  hubs.json   the list of hubs (one line per hub)
scripts/
  test.py     runs unit tests or the smoke check
tests/        unit tests
```

## Data storage choice
TBD (planned: SQLite)

## Assumptions
- Hubs are fictional, located in real US cities.
- Regions follow the US Census Bureau definition (Northeast, Midwest, South, West).

## Limitations
TBD
