"""Download JSON from a public API, using the SQLite cache.

Uses the Python standard library (urllib). certifi provides trusted HTTPS
certificates, so it works the same on every OS (some Python installs on
macOS have none by default).
"""

import json
import ssl
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi

from app import cache

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Open-Meteo's free tier has a per-minute limit. When we hit it (HTTP 429),
# wait and try again instead of failing.
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 30


def fetch_json(url, params, db_path=cache.DB_PATH, use_cache=True):
    """Return the JSON response for url + params, from the cache if possible.

    use_cache=False always downloads and stores nothing: for data that
    changes, like forecasts.
    """
    full_url = url + "?" + urlencode(params)

    if use_cache:
        cached = cache.get(full_url, db_path)
        if cached is not None:
            return cached

    data = _download_with_retry(full_url)

    # Some APIs report errors inside a normal-looking response.
    # Raise instead of caching them, so a later call can retry.
    if isinstance(data, dict) and data.get("error"):
        raise ValueError(f"API returned an error for {full_url}: {data}")

    if use_cache:
        cache.set(full_url, data, db_path)
    return data


def _download_with_retry(full_url):
    """Download, waiting and retrying if the API says we sent too many requests."""
    for attempt in range(RATE_LIMIT_RETRIES):
        try:
            return _download(full_url)
        except HTTPError as error:
            if error.code != 429 or attempt == RATE_LIMIT_RETRIES - 1:
                raise
            time.sleep(RATE_LIMIT_WAIT_SECONDS)


def _download(full_url):
    """Send the HTTP GET request. Kept separate so tests can replace it."""
    with urlopen(full_url, timeout=60, context=SSL_CONTEXT) as response:
        return json.load(response)
