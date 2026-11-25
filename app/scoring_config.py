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
#
# Each day also gets a RELATIVE score: how unusual the value is for this
# hub in this calendar month (-8 °C is extreme in Dallas, normal in
# Minneapolis). It counts only on a DISRUPTIVE day, by the same daily
# definitions as the long-term metrics above ("disruptive_from": a snow
# day, heavy rain day, windy day, hot day, freezing night). A hazard's day
# score is the higher of the absolute and the relative score.
# An unusual day that is not disruptive only becomes an info note.
FORECAST_DAYS = 7
FORECAST_SCALES = {
    "snow": {"variable": "snowfall_cm", "zero_at": 0, "full_at": 15,
             "disruptive_from": SNOW_DAY_MIN_CM, "unit": "cm"},
    "heavy_rain": {"variable": "precipitation_mm", "zero_at": 10, "full_at": 50,
                   "disruptive_from": HEAVY_RAIN_MIN_MM, "unit": "mm"},
    "wind": {"variable": "wind_gust_max_kmh", "zero_at": 40, "full_at": 100,
             "disruptive_from": WINDY_DAY_MIN_KMH, "unit": "km/h"},
    "heat": {"variable": "temp_max_c", "zero_at": 30, "full_at": 42,
             "disruptive_from": HOT_DAY_MIN_C, "unit": "°C"},
    "cold": {"variable": "temp_min_c", "zero_at": -10, "full_at": -30,
             "disruptive_from": FREEZING_DAY_MAX_C, "unit": "°C"},
}

# Relative score: the value's percentile among the hub's past days of the
# same calendar month (share of days that were less severe). 0 up to this
# percentile, rising linearly to 100 beyond the most extreme past day.
# 95, not lower: with ~150 past days per month and 35 hazard-days per
# forecast, a lower start makes almost every hub score high.
# The same percentile marks an "unusual" day for the info notes.
RELATIVE_FROM_PERCENTILE = 95

# Alert when a hub's short-term score is at least ALERT_MIN_CHANGE points
# away from any of its scores in the last ALERT_WINDOW_DAYS days (only
# counting checks since its last alert). The window catches gradual rises,
# not only jumps since the previous check. Forecasts change daily: smaller
# moves are noise.
ALERT_MIN_CHANGE = 10
ALERT_WINDOW_DAYS = 3
# ...and only when the old or the new score is at least this high: a move
# between two low scores (e.g. 14 -> 28) is not worth an alert.
ALERT_MIN_LEVEL = 40
