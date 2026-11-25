"""Run the project's checks. Works on every OS.

    python scripts/test.py          # unit tests (mocked, fast, free)
    python scripts/test.py smoke    # one real API call, run by hand
"""

import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))  # so "import app" works from any folder


def run_unit_tests():
    # -q: short output; --tb=short: only the key lines of each failure.
    command = [sys.executable, "-m", "pytest", "-q", "--tb=short", "tests"]
    return subprocess.run(command, cwd=PROJECT_ROOT).returncode


def run_smoke_check():
    """Call each real API once for Denver. Uses a temporary cache file,
    so it always hits the network and never touches data/cache.db."""
    from app import metrics, nri, weather

    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "smoke.db"

        risk = nri.fetch_county_risk("08031", db)
        print(f"NRI OK: {risk['county']}, {risk['state']} "
              f"({risk['nri_version']}), winter weather "
              f"{risk['hazards']['winter_weather']['frequency']:.1f} events/year, "
              f"national percentile "
              f"{risk['hazards']['winter_weather']['frequency_percentile']}")

        days = weather.fetch_daily_weather(
            39.7392, -104.9903, date(2025, 1, 1), date(2025, 12, 31), db
        )
        m = metrics.compute_metrics(days)
        print(f"Open-Meteo OK: {m['days']} days in 2025, "
              f"{m['snow_days']} with snowfall ({m['snow_days_pct']}%)")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "unit"
    if mode == "unit":
        sys.exit(run_unit_tests())
    elif mode == "smoke":
        sys.exit(run_smoke_check())
    else:
        print(f"Unknown mode '{mode}'. Use: python scripts/test.py [smoke]")
        sys.exit(2)
