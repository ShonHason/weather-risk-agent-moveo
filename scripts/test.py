"""Run the project's checks. Works on every OS.

    python scripts/test.py          # unit tests (mocked, fast, free)
    python scripts/test.py smoke    # one real API call, run by hand
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def run_unit_tests():
    # -q: short output; --tb=short: only the key lines of each failure.
    command = [sys.executable, "-m", "pytest", "-q", "--tb=short", "tests"]
    return subprocess.run(command, cwd=PROJECT_ROOT).returncode


def run_smoke_check():
    # Placeholder until step 2, when the real API clients exist.
    print("Smoke check: nothing to check yet (added in step 2).")
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
