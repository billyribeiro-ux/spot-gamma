"""Shared HTTP session with retry/backoff for the vendor adapters.

A single transient network blip or 5xx shouldn't fail an entire chain request
(and for Polygon, a mid-pagination failure shouldn't discard prior pages). All
networked sources go through :func:`session`, which returns a ``requests.Session``
pre-mounted with exponential-backoff retries on idempotent failures.

The session is thread-local: the API runs sync handlers in a threadpool and a
``requests.Session`` is not guaranteed safe to share across threads, so each
worker thread gets its own.
"""

from __future__ import annotations

import threading

_local = threading.local()

# Retry on connection errors + the usual transient statuses, with backoff
# (0.5s, 1s, 2s). raise_on_status=False so callers keep doing .raise_for_status().
_RETRY_KW = {
    "total": 3,
    "backoff_factor": 0.5,
    "status_forcelist": (429, 500, 502, 503, 504),
    "raise_on_status": False,
}


def session():
    """Return this thread's shared retrying ``requests.Session``."""
    s = getattr(_local, "session", None)
    if s is None:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry = Retry(allowed_methods=frozenset(["GET", "POST"]), **_RETRY_KW)
        adapter = HTTPAdapter(max_retries=retry)
        s = requests.Session()
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _local.session = s
    return s
