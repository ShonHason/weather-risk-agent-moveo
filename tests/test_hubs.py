"""Check that data/hubs.json is valid, so a typo in a new hub is caught early."""

from app.hubs import STATE_TO_REGION, load_hubs

REQUIRED_FIELDS = ["id", "name", "city", "state", "lat", "lon", "county_fips"]


def test_every_hub_has_required_fields():
    for hub in load_hubs():
        for field in REQUIRED_FIELDS:
            assert field in hub, f"{hub.get('id')} is missing '{field}'"


def test_hub_ids_are_unique():
    ids = [hub["id"] for hub in load_hubs()]
    assert len(ids) == len(set(ids))


def test_coordinates_are_inside_the_us():
    for hub in load_hubs():
        assert 18 <= hub["lat"] <= 72, hub["id"]
        assert -180 <= hub["lon"] <= -65, hub["id"]


def test_county_fips_is_five_digits():
    for hub in load_hubs():
        fips = hub["county_fips"]
        assert len(fips) == 5 and fips.isdigit(), hub["id"]


def test_fips_matches_state_prefix():
    # The first two digits of a county FIPS code identify the state.
    state_fips = {
        "IL": "17", "MN": "27", "MI": "26", "MO": "29", "IN": "18", "OH": "39",
        "CO": "08", "WA": "53", "CA": "06", "AZ": "04", "UT": "49", "TX": "48",
        "FL": "12", "GA": "13", "LA": "22", "TN": "47", "NJ": "34", "MA": "25",
        "PA": "42", "NY": "36",
    }
    for hub in load_hubs():
        if hub["state"] in state_fips:
            assert hub["county_fips"][:2] == state_fips[hub["state"]], hub["id"]


def test_every_hub_gets_a_region():
    for hub in load_hubs():
        assert hub["region"] in {"Northeast", "Midwest", "South", "West"}


def test_all_four_regions_are_covered():
    regions = {hub["region"] for hub in load_hubs()}
    assert regions == set(STATE_TO_REGION.values())
