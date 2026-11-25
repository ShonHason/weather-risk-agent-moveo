"""FEMA National Risk Index (NRI) client: hazard risk scores for one county.

Source: FEMA's official ArcGIS service "National Risk Index Counties".
No API key is needed. NRI scores are national percentiles (0-100): a score of
90 means the county's risk is higher than 90% of US counties.
"""

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


def fetch_county_risk(county_fips, db_path=cache.DB_PATH):
    """Return the NRI risk scores for one county.

    Example result:
        {"county": "Denver", "state": "CO", "nri_version": "December 2025",
         "overall": {"score": 95.2, "rating": "Relatively High"},
         "hazards": {"hail": {"score": 99.9, "rating": "Very High"}, ...}}

    A hazard that does not apply to the county (e.g. hurricane in Denver)
    has score None and rating "Not Applicable".
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

    hazards = {}
    for prefix, name in NRI_HAZARDS.items():
        hazards[name] = {
            "score": attributes.get(f"{prefix}_RISKS"),
            "rating": attributes.get(f"{prefix}_RISKR"),
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
