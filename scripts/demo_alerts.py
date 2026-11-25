"""Demo of the risk-change alert, without editing any config file.

    python scripts/demo_alerts.py

1. starts from a clean, temporary history (data/history.db is not touched);
2. runs a baseline check on the real 7-day forecast;
3. makes the wind scale stricter, IN MEMORY ONLY (gusts of 70 km/h count
   as 100 instead of 100 km/h), as if the forecast had turned windier;
4. runs the check again: hubs whose score jumps raise alerts, which are
   sent to ALERT_WEBHOOK_URL (from .env) if it is set;
5. puts the scale back and deletes the temporary history.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # so "import app" works

from app import alerts
from app import scoring_config as config
from app.env import load_env

DEMO_WIND_FULL_AT = 70   # km/h; the real value is in app/scoring_config.py


def main():
    load_env()
    wind = config.FORECAST_SCALES["wind"]
    real_full_at = wind["full_at"]

    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "demo_history.db"

        print("1. Baseline check (real forecast, clean history)...")
        baseline = alerts.run_check(db)
        print(f"   {len(baseline['new_baselines'])} hubs saved, no alerts.")

        print(f"2. Wind scale in memory: {real_full_at} -> {DEMO_WIND_FULL_AT} km/h "
              "= score 100 (config files unchanged).")
        wind["full_at"] = DEMO_WIND_FULL_AT
        try:
            print("3. Second check...")
            result = alerts.run_check(db)
        finally:
            wind["full_at"] = real_full_at   # always put it back

    print(f"   {len(result['alerts'])} alerts, webhook: {result['webhook']}\n")
    if result["alerts"]:
        print(alerts.summary_text(result["alerts"]))   # the "text" that is sent
    if result["webhook"] == "not configured":
        print("\nSet ALERT_WEBHOOK_URL in .env to send the alerts to a webhook.")


if __name__ == "__main__":
    main()
