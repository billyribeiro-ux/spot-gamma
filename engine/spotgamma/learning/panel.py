"""Point-in-time historical panel for the backtest/learning layer.

Assembles a daily, **point-in-time-correct** panel of the market-structure
inputs that have clean free history:

* ``vix``      — CBOE VIX close (FRED ``VIXCLS``, ~11y)
* ``vix3m``    — 3-month VIX (FRED ``VXVCLS``, ~11y)
* ``vvix``     — vol-of-vol (Yahoo ``^VVIX``, ~10y; not on FRED)
* ``hy_oas``   — ICE BofA HY OAS (FRED ``BAMLH0A0HYM2``; the free CSV path serves
                 ~3y, which bounds any HY-dependent window — surfaced, not hidden)
* ``spread``   — 2s10s (FRED ``T10Y2Y``, ~11y)
* ``dxy``      — broad dollar (FRED ``DTWEXBGS``, ~11y)
* ``spy``      — SPY close (Yahoo, ~10y) — the underlying for forward-return labels

Breadth, put/call, and dealer-gamma sign are intentionally **excluded** from the
historical panel: none has clean free *history* (breadth needs ~500 constituent
back-histories, put/call needs historical chain volumes, gamma sign needs
historical chains). The backtest therefore answers the §7 question for the
vol+macro signals — the ones it *can* answer honestly — and says so.

Point-in-time rule: the panel is indexed on SPY trading dates; each series
contributes its **last value observed on or before** that date (macro series
publish on lags and only on business days, so as-of carry-forward is the correct
information set a trader had at the close of *t*). Parsing/alignment are pure and
unit-tested; only ``fetch_*`` touch the network.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import UTC, date, datetime
from typing import NamedTuple

# Friendly feature name -> FRED series id (macro inputs with deep free history).
FRED_SERIES: dict[str, str] = {
    "vix": "VIXCLS",
    "vix3m": "VXVCLS",
    "hy_oas": "BAMLH0A0HYM2",
    "spread": "T10Y2Y",
    "dxy": "DTWEXBGS",
}
# Friendly feature name -> Yahoo ticker (series Yahoo carries but FRED doesn't,
# plus SPY for labels).
YAHOO_SERIES: dict[str, str] = {
    "vvix": "^VVIX",
    "spy": "SPY",
}

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


class Observation(NamedTuple):
    date: date
    value: float


class PanelRow(NamedTuple):
    """One trading date with the as-of value of every series (None if not yet known)."""

    date: date
    values: dict[str, float | None]


def parse_yahoo_daily(payload: dict) -> list[Observation]:
    """Yahoo v8 chart payload -> chronological daily ``(date, close)`` (pure).

    Drops null buckets (halted/illiquid sessions). Epoch timestamps are converted
    on the UTC calendar — unambiguous for daily bars.
    """
    result = (payload.get("chart") or {}).get("result")
    if not result:
        err = (payload.get("chart") or {}).get("error")
        raise ValueError(f"Yahoo chart error: {err}" if err else "empty Yahoo chart response")
    r = result[0]
    timestamps = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    out: list[Observation] = []
    for i, t in enumerate(timestamps):
        c = closes[i] if i < len(closes) else None
        if t is None or c is None:
            continue
        out.append(Observation(datetime.fromtimestamp(int(t), UTC).date(), float(c)))
    out.sort(key=lambda o: o.date)
    return out


def _dedupe_last(obs: list[Observation]) -> list[Observation]:
    """Collapse same-date observations to the last one, preserving order."""
    by_date: dict[date, float] = {}
    for o in obs:
        by_date[o.date] = o.value
    return [Observation(d, by_date[d]) for d in sorted(by_date)]


class AsOf:
    """As-of lookup over a chronological series: value last observed on/before a date."""

    def __init__(self, obs: list[Observation]) -> None:
        clean = _dedupe_last(obs)
        self._dates = [o.date for o in clean]
        self._values = [o.value for o in clean]

    def __bool__(self) -> bool:
        return bool(self._dates)

    def at(self, d: date) -> float | None:
        """Last value observed on or before ``d`` (None if ``d`` precedes all data)."""
        i = bisect_right(self._dates, d)
        return self._values[i - 1] if i else None


def build_panel(
    series: dict[str, list[Observation]],
    *,
    calendar_key: str = "spy",
) -> list[PanelRow]:
    """Align raw series into a point-in-time daily panel on ``calendar_key``'s dates.

    The calendar series (default SPY) defines the trading dates; every other
    series contributes its as-of value (last observed on/before each date). The
    first row is the earliest calendar date on which the calendar series itself
    exists. Pure: no network, deterministic for a given input.
    """
    if calendar_key not in series or not series[calendar_key]:
        return []
    asof = {name: AsOf(obs) for name, obs in series.items()}
    calendar = _dedupe_last(series[calendar_key])
    rows: list[PanelRow] = []
    for o in calendar:
        rows.append(PanelRow(o.date, {name: asof[name].at(o.date) for name in series}))
    return rows


def coverage(panel: list[PanelRow]) -> dict[str, dict]:
    """Per-series non-null coverage over the panel (for honest window reporting)."""
    if not panel:
        return {}
    names = list(panel[0].values)
    out: dict[str, dict] = {}
    for name in names:
        present = [r.date for r in panel if r.values.get(name) is not None]
        out[name] = {
            "n": len(present),
            "first": present[0].isoformat() if present else None,
            "last": present[-1].isoformat() if present else None,
        }
    return out


# --- network (thin; everything above is pure) ------------------------------
def fetch_yahoo_daily(ticker: str, range_: str = "10y") -> list[Observation]:
    """Fetch a long daily history from Yahoo (default 10y — not the 1y UI cap)."""
    from ..marketstructure._http_ms import session

    resp = session().get(
        _CHART_URL.format(ticker=ticker),
        params={"interval": "1d", "range": range_},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_yahoo_daily(resp.json())


def fetch_fred(series_id: str, observation_start: str = "2010-01-01") -> list[Observation]:
    """Fetch a FRED series as chronological observations (deepest available)."""
    from ..marketstructure.fred import fetch_series

    return [Observation(p.date, p.value) for p in fetch_series(series_id, observation_start)]


def fetch_panel(*, range_: str = "10y", observation_start: str = "2010-01-01") -> list[PanelRow]:
    """Fetch and align the full historical panel from FRED + Yahoo (network)."""
    series: dict[str, list[Observation]] = {}
    for name, sid in FRED_SERIES.items():
        series[name] = fetch_fred(sid, observation_start)
    for name, ticker in YAHOO_SERIES.items():
        series[name] = fetch_yahoo_daily(ticker, range_)
    return build_panel(series, calendar_key="spy")
