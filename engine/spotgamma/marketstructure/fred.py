"""FRED data via the public ``fredgraph.csv`` export — no API key required.

The St. Louis Fed serves every series as CSV at
``https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES}`` with no
authentication, which is the same "real data, no key" spirit as the Cboe and
Yahoo sources. Parsing is a pure function so it's unit-tested without the
network.

Series used by the market-structure signals (see docs/MARKET_STRUCTURE.md):
- ``DGS10``        10-Year Treasury yield (%)
- ``T10Y2Y``       10Y-2Y spread (%) — inversion (< 0) is a recession signal
- ``BAMLH0A0HYM2`` ICE BofA US High-Yield OAS (%) — credit stress gauge
- ``DTWEXBGS``     Nominal Broad US Dollar Index
- ``VIXCLS``       CBOE VIX close (FRED fallback for Yahoo ^VIX)
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple

_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FredPoint(NamedTuple):
    date: date
    value: float


def parse_fred_csv(text: str) -> list[FredPoint]:
    """Parse a fredgraph CSV into ``(date, value)`` points (pure).

    Format is a header row (``observation_date,SERIES``) then ``YYYY-MM-DD,value``
    rows; FRED writes ``.`` for missing observations, which are skipped.
    """
    out: list[FredPoint] = []
    lines = text.strip().splitlines()
    for line in lines[1:]:  # skip header
        parts = line.split(",")
        if len(parts) < 2:
            continue
        raw_date, raw_val = parts[0].strip(), parts[1].strip()
        if not raw_val or raw_val == ".":
            continue
        try:
            d = date.fromisoformat(raw_date)
            v = float(raw_val)
        except ValueError:
            continue
        out.append(FredPoint(d, v))
    return out


def latest(points: list[FredPoint]) -> FredPoint | None:
    """Most recent observation (the CSV is chronological), or None if empty."""
    return points[-1] if points else None


def fetch_series(series_id: str, observation_start: str | None = None) -> list[FredPoint]:
    """Fetch a FRED series as ``(date, value)`` points (no API key)."""
    from ._http_ms import session

    params = {"id": series_id}
    if observation_start:
        params["cosd"] = observation_start
    resp = session().get(_BASE, params=params, timeout=20, headers=_FRED_HEADERS)
    resp.raise_for_status()
    return parse_fred_csv(resp.text)


# FRED's CDN 503s browser-style and custom UAs (the shared session sends a browser
# UA for Yahoo), but accepts a plain library UA. Yahoo and FRED have *opposite* UA
# requirements, so every FRED request must override the session default with this.
_FRED_HEADERS = {"User-Agent": "python-requests/2.31.0"}
