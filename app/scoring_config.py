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


# --- Short-term (7-day forecast) risk score, used by the alert -------------
# Separate from the long-term score above. For each hazard: the worst
# forecast day, on a linear scale from "no impact" (0) to "severe" (100),
# capped. A hub's short-term score is its worst hazard (the max).
FORECAST_DAYS = 7
FORECAST_SCALES = {
    "snow": {"variable": "snowfall_cm", "zero_at": 0, "full_at": 15, "unit": "cm"},
    "heavy_rain": {"variable": "precipitation_mm", "zero_at": 10, "full_at": 50, "unit": "mm"},
    "wind": {"variable": "wind_gust_max_kmh", "zero_at": 40, "full_at": 100, "unit": "km/h"},
    "heat": {"variable": "temp_max_c", "zero_at": 30, "full_at": 42, "unit": "°C"},
    "cold": {"variable": "temp_min_c", "zero_at": -10, "full_at": -30, "unit": "°C"},
}

# Alert when a hub's short-term score moves by at least this many points
# since the last check. Forecasts change daily: smaller moves are noise.
ALERT_MIN_CHANGE = 10
