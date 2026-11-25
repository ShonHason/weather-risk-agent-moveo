"""Load the list of hubs from data/hubs.json.

To add a hub, add one line to data/hubs.json. The region is not stored in the
file: it is derived from the state, using the US Census Bureau regions.
"""

import json
from pathlib import Path

HUBS_FILE = Path(__file__).parent.parent / "data" / "hubs.json"

# US Census Bureau regions (50 states + DC).
STATE_TO_REGION = {
    # Northeast
    "CT": "Northeast", "ME": "Northeast", "MA": "Northeast", "NH": "Northeast",
    "RI": "Northeast", "VT": "Northeast", "NJ": "Northeast", "NY": "Northeast",
    "PA": "Northeast",
    # Midwest
    "IL": "Midwest", "IN": "Midwest", "MI": "Midwest", "OH": "Midwest",
    "WI": "Midwest", "IA": "Midwest", "KS": "Midwest", "MN": "Midwest",
    "MO": "Midwest", "NE": "Midwest", "ND": "Midwest", "SD": "Midwest",
    # South
    "DE": "South", "DC": "South", "FL": "South", "GA": "South", "MD": "South",
    "NC": "South", "SC": "South", "VA": "South", "WV": "South", "AL": "South",
    "KY": "South", "MS": "South", "TN": "South", "AR": "South", "LA": "South",
    "OK": "South", "TX": "South",
    # West
    "AZ": "West", "CO": "West", "ID": "West", "MT": "West", "NV": "West",
    "NM": "West", "UT": "West", "WY": "West", "AK": "West", "CA": "West",
    "HI": "West", "OR": "West", "WA": "West",
}


def load_hubs(path=HUBS_FILE):
    """Return the list of hubs, each with its region added."""
    with open(path) as f:
        hubs = json.load(f)
    for hub in hubs:
        hub["region"] = STATE_TO_REGION[hub["state"]]
    return hubs
