"""Underlying price history for the dashboard's trading chart.

The gamma engine computes levels from an option chain; it has no price series.
The TradingView lightweight-charts panel needs OHLC bars across timeframes, so
this module provides them from a free, no-account source (Yahoo's public v8
chart endpoint) — the same "real data, no key" spirit as the Cboe chain source.
Index symbols map to Yahoo's ``^`` tickers; ETFs pass through.

Parsing is a pure function (:func:`parse_yahoo_chart`) so it's unit-tested
without the network. A broker/vendor source with native history (Polygon
aggregates, Schwab pricehistory) can be layered in later behind the same shape.
"""

from __future__ import annotations

from typing import NamedTuple

# UI timeframe -> (Yahoo interval, Yahoo range). Ranges respect Yahoo's caps
# (1m only spans a few days; 60m up to ~2y).
TIMEFRAMES: dict[str, tuple[str, str]] = {
    "1m": ("1m", "1d"),
    "5m": ("5m", "5d"),
    "15m": ("15m", "5d"),
    "30m": ("30m", "1mo"),
    "1h": ("60m", "3mo"),
    "1D": ("1d", "1y"),
    "1W": ("1wk", "5y"),
    "1M": ("1mo", "max"),
}
DEFAULT_TIMEFRAME = "5m"

# Cash-index symbols Yahoo serves under a caret ticker; everything else passes through.
_YAHOO_SYMBOL: dict[str, str] = {
    "SPX": "^GSPC",
    "NDX": "^NDX",
    "RUT": "^RUT",
    "VIX": "^VIX",
    "DJX": "^DJI",
    "XSP": "^XSP",
}

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class Bar(NamedTuple):
    time: int  # epoch seconds (UTC), as lightweight-charts expects
    open: float
    high: float
    low: float
    close: float
    volume: float


def yahoo_symbol(symbol: str) -> str:
    s = symbol.upper()
    return _YAHOO_SYMBOL.get(s, s)


def resolve_timeframe(tf: str | None) -> tuple[str, str, str]:
    """Return (ui_token, yahoo_interval, yahoo_range) for a requested timeframe."""
    token = tf if tf in TIMEFRAMES else DEFAULT_TIMEFRAME
    interval, rng = TIMEFRAMES[token]
    return token, interval, rng


def parse_yahoo_chart(payload: dict) -> tuple[list[Bar], dict]:
    """Normalize a Yahoo v8 chart payload into (bars, meta). Pure.

    Yahoo emits parallel arrays with occasional ``null`` gaps (illiquid/halted
    buckets); those rows are dropped so the chart never renders a broken candle.
    """
    result = (payload.get("chart") or {}).get("result")
    if not result:
        err = (payload.get("chart") or {}).get("error")
        raise ValueError(f"Yahoo chart error: {err}" if err else "empty Yahoo chart response")
    r = result[0]
    meta = r.get("meta", {})
    timestamps = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    o, h, low, c, v = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))

    bars: list[Bar] = []
    for i, t in enumerate(timestamps):
        op, hi, lo, cl = o[i], h[i], low[i], c[i]
        if None in (op, hi, lo, cl):
            continue  # skip gap buckets
        bars.append(Bar(int(t), float(op), float(hi), float(lo), float(cl), float(v[i] or 0)))
    summary = {
        "symbol": meta.get("symbol"),
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName"),
        "last_price": meta.get("regularMarketPrice"),
    }
    return bars, summary


def fetch_history(symbol: str, timeframe: str | None = None) -> dict:
    """Fetch OHLC bars for ``symbol`` at the requested timeframe (Yahoo, free)."""
    import requests

    token, interval, rng = resolve_timeframe(timeframe)
    resp = requests.get(
        _CHART_URL.format(symbol=yahoo_symbol(symbol)),
        params={"interval": interval, "range": rng, "includePrePost": "false"},
        headers={"User-Agent": "Mozilla/5.0 (spotgamma)"},
        timeout=20,
    )
    resp.raise_for_status()
    bars, summary = parse_yahoo_chart(resp.json())
    return {
        "symbol": symbol.upper(),
        "timeframe": token,
        "bars": [b._asdict() for b in bars],
        "meta": summary,
    }
