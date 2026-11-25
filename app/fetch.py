"""Download JSON from a public API, using the SQLite cache.

Uses the Python standard library (urllib). certifi provides trusted HTTPS
certificates, so it works the same on every OS (some Python installs on
macOS have none by default).
"""

import json
import ssl
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi

from app import cache

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def fetch_json(url, params, db_path=cache.DB_PATH):
    """Return the JSON response for url + params, from the cache if possible."""
    full_url = url + "?" + urlencode(params)

    cached = cache.get(full_url, db_path)
    if cached is not None:
        return cached

    data = _download(full_url)

    # Some APIs report errors inside a normal-looking response.
    # Raise instead of caching them, so a later call can retry.
    if isinstance(data, dict) and data.get("error"):
        raise ValueError(f"API returned an error for {full_url}: {data}")

    cache.set(full_url, data, db_path)
    return data


def _download(full_url):
    """Send the HTTP GET request. Kept separate so tests can replace it."""
    with urlopen(full_url, timeout=60, context=SSL_CONTEXT) as response:
        return json.load(response)
