"""All the numbers behind the risk score, in one place.

Change a weight or a scale here; no other file needs to change.
"""

# Our five hazard categories, and the NRI hazards that feed each one.
# A category's NRI score is its WORST hazard (the max), because one severe
# hazard is enough to shut a hub down.
CATEGORY_HAZARDS = {
    "winter": ["winter_weather", "ice_storm", "cold_wave"],
    "hurricane": ["hurricane"],
    "flood": ["inland_flooding", "coastal_flooding"],
    "severe_storm": ["tornado", "strong_wind", "hail"],
    "heat": ["heat_wave"],
}

# How much each category counts in the overall score (sums to 1).
CATEGORY_WEIGHTS = {
    "winter": 0.20,
    "hurricane": 0.20,
    "flood": 0.20,
    "severe_storm": 0.20,
    "heat": 0.20,
}

# Chronic hazards happen every year, so 5 years of observed weather is a
# fair sample: their score blends NRI with what was actually observed.
# Acute hazards (hurricane, severe storm) are rare in any one place, so
# 5 years tells us little: their score is NRI only (NRI is built from
# decades of event records).
NRI_SHARE = 0.7
OBSERVED_SHARE = 0.3

# For each chronic category: which observed metric to use (a yearly
# average), and the value that maps to a full 100. Linear from 0, capped.
OBSERVED_SCALES = {
    "winter": {"metric": "snow_days_per_year", "full_score_at": 40},
    "heat": {"metric": "hot_days_per_year", "full_score_at": 60},
    "flood": {"metric": "heavy_rain_days_per_year", "full_score_at": 15},
}

# Thresholds that define the daily weather metrics.
SNOW_DAY_MIN_CM = 0.1        # any measurable snowfall
HEAVY_RAIN_MIN_MM = 25.0     # about 1 inch of rain in a day
HOT_DAY_MIN_C = 35.0         # about 95 °F
FREEZING_DAY_MAX_C = 0.0     # minimum temperature below freezing
WINDY_DAY_MIN_KMH = 60.0     # gusts strong enough to disrupt trucks
