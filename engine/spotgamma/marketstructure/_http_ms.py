"""Thread-local retrying HTTP session for market-structure fetchers.

Mirrors ``sources/_http.py`` (same retry/backoff rationale) but kept separate so
the market-structure package has no import dependency on the chain sources.
"""

from __future__ import annotations

import threading

_local = threading.local()

# Fail-fast policy: these feeds are cached (MS_TTL) and degrade gracefully, so
# patient retrying is wrong here. Crucially, respect_retry_after_header=False —
# Yahoo's 429s carry Retry-After of 60s+, which once turned a single read into
# ~90s of dutiful waiting. Two quick attempts with a capped backoff, then degrade.
_RETRY_KW = {
    "total": 2,
    "backoff_factor": 0.3,
    "backoff_max": 2.0,
    "status_forcelist": (429, 500, 502, 503, 504),
    "raise_on_status": False,
    "respect_retry_after_header": False,
}


def session():
    """Return this thread's shared retrying ``requests.Session``."""
    s = getattr(_local, "session", None)
    if s is None:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry = Retry(allowed_methods=frozenset(["GET"]), **_RETRY_KW)
        adapter = HTTPAdapter(max_retries=retry)
        s = requests.Session()
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        # Yahoo rejects the default python-requests UA on some endpoints.
        s.headers.update({"User-Agent": "Mozilla/5.0 (spotgamma market-structure)"})
        _local.session = s
    return s
