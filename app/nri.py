"""FEMA National Risk Index (NRI) client: hazard data for one county.

Source: FEMA's official ArcGIS service "National Risk Index Counties".
No API key is needed.

Per hazard we use two NRI fields:
- AFREQ (annualized frequency): how many events (or event-days) of this
  hazard the county has per year. This is what drives our score, turned into
  a national percentile: 90 means more frequent than in 90% of US counties.
- RISKS (risk score): FEMA's official community risk percentile. It also
  counts the property and population exposed, so big counties score high on
  almost everything. Returned as context only, not used in our score.
"""

from bisect import bisect_left

from app import cache
from app.fetch import fetch_json

NRI_COUNTIES_URL = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
    "National_Risk_Index_Counties/FeatureServer/0/query"
)

# The NRI hazards we use, by their NRI field prefix.
# Each one later feeds one of our five hazard categories (see PLAN.md).
NRI_HAZARDS = {
    "WNTW": "winter_weather",
    "ISTM": "ice_storm",
    "CWAV": "cold_wave",
    "HRCN": "hurricane",
    "IFLD": "inland_flooding",
    "CFLD": "coastal_flooding",
    "TRND": "tornado",
    "SWND": "strong_wind",
    "HAIL": "hail",
    "HWAV": "heat_wave",
}

# Most counties the service returns in one request.
PAGE_SIZE = 2000


def fetch_county_risk(county_fips, db_path=cache.DB_PATH):
    """Return the NRI hazard data for one county.

    Example result:
        {"county": "Denver", "state": "CO", "nri_version": "December 2025",
         "overall": {"score": 95.2, "rating": "Relatively High"},
         "hazards": {"hail": {"frequency": 2.1, "frequency_percentile": 93.4,
                              "risk_score": 99.9, "risk_rating": "Very High"},
                     ...}}

    A hazard that does not apply to the county (e.g. hurricane in Denver)
    has frequency None and frequency_percentile 0.
    """
    params = {
        "where": f"STCOFIPS='{county_fips}'",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }
    data = fetch_json(NRI_COUNTIES_URL, params, db_path)

    if not data.get("features"):
        raise ValueError(f"No NRI data found for county FIPS {county_fips}")
    attributes = data["features"][0]["attributes"]

    all_counties = national_frequencies(db_path)
    hazards = {}
    for prefix, name in NRI_HAZARDS.items():
        frequency = attributes.get(f"{prefix}_AFREQ")
        hazards[name] = {
            "frequency": frequency,
            "frequency_percentile": percentile(frequency, all_counties[name]),
            "risk_score": attributes.get(f"{prefix}_RISKS"),
            "risk_rating": attributes.get(f"{prefix}_RISKR"),
        }

    return {
        "county": attributes.get("COUNTY"),
        "state": attributes.get("STATEABBRV"),
        "nri_version": attributes.get("NRI_VER"),
        "overall": {
            "score": attributes.get("RISK_SCORE"),
            "rating": attributes.get("RISK_RATNG"),
        },
        "hazards": hazards,
    }


def national_frequencies(db_path=cache.DB_PATH):
    """The yearly frequency of each hazard in every US county, sorted.

    Downloaded page by page (the service returns at most 2000 counties per
    request), then cached like any other response.
    Not applicable (None) counts as 0: the hazard does not happen there.
    """
    fields = [f"{prefix}_AFREQ" for prefix in NRI_HAZARDS]
    frequencies = {name: [] for name in NRI_HAZARDS.values()}
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": ",".join(fields),
            "returnGeometry": "false",
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "f": "json",
        }
        features = fetch_json(NRI_COUNTIES_URL, params, db_path)["features"]
        for feature in features:
            for prefix, name in NRI_HAZARDS.items():
                frequencies[name].append(feature["attributes"][f"{prefix}_AFREQ"] or 0.0)
        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return {name: sorted(values) for name, values in frequencies.items()}


def percentile(value, sorted_values):
    """Percent of values strictly lower than value (0-100). None counts as 0."""
    lower = bisect_left(sorted_values, value or 0.0)
    return round(100 * lower / len(sorted_values), 1)
