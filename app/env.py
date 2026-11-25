"""Load settings (like ANTHROPIC_API_KEY) from the .env file.

A few lines instead of the python-dotenv package: KEY=value per line,
'#' starts a comment. Variables already set in the environment win.
"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent / ".env"


def load_env(path=ENV_FILE):
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
