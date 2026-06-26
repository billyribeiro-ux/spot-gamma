"""Spot quotes for market-structure tickers via Yahoo's free v8 chart endpoint.

Reuses the same no-key Yahoo source as ``history.py`` but returns just the
latest value (and prior close, for day-change) for the indices the
market-structure signals need: ^VIX, ^VIX3M, ^VVIX, ^TNX, DX-Y.NYB.

Parsing is a pure function so it's unit-tested without the network.
"""

from __future__ import annotations

from typing import NamedTuple

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

# Friendly name -> Yahoo ticker. ^TNX quotes 10x the 10Y yield.
TICKERS: dict[str, str] = {
    "vix": "^VIX",
    "vix3m": "^VIX3M",
    "vvix": "^VVIX",
    "tnx": "^TNX",
    "dxy": "DX-Y.NYB",
}


class Quote(NamedTuple):
    symbol: str
    price: float
    prev_close: float | None

    @property
    def change(self) -> float | None:
        if self.prev_close is None or self.prev_close == 0:
            return None
        return self.price - self.prev_close

    @property
    def change_pct(self) -> float | None:
        if self.prev_close is None or self.prev_close == 0:
            return None
        return (self.price - self.prev_close) / self.prev_close * 100.0


def parse_yahoo_quote(payload: dict) -> Quote:
    """Extract (symbol, price, prev_close) from a Yahoo v8 chart payload (pure)."""
    result = (payload.get("chart") or {}).get("result")
    if not result:
        err = (payload.get("chart") or {}).get("error")
        raise ValueError(f"Yahoo quote error: {err}" if err else "empty Yahoo quote response")
    meta = result[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    if price is None:
        raise ValueError("Yahoo quote payload missing regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    return Quote(symbol=meta.get("symbol", ""), price=float(price), prev_close=float(prev) if prev else None)


def fetch_quote(ticker: str) -> Quote:
    """Fetch a single Yahoo quote (latest price + prior close)."""
    from ._http_ms import session

    resp = session().get(
        _CHART_URL.format(ticker=ticker),
        params={"interval": "1d", "range": "5d"},
        timeout=8,
    )
    resp.raise_for_status()
    return parse_yahoo_quote(resp.json())


def parse_yahoo_closes(payload: dict) -> list[float]:
    """Chronological daily closes from a Yahoo v8 chart payload (pure).

    Drops null buckets (halted/illiquid sessions). Used for trend statistics
    (e.g. the dollar's 200-DMA and 20-day rate-of-change) that a single quote
    can't supply.
    """
    result = (payload.get("chart") or {}).get("result")
    if not result:
        return []
    quote = ((result[0].get("indicators") or {}).get("quote") or [{}])[0]
    return [float(c) for c in (quote.get("close") or []) if c is not None]


def fetch_daily_closes(ticker: str, range_: str = "1y") -> list[float]:
    """Daily close history for ``ticker`` (most recent last)."""
    from ._http_ms import session

    resp = session().get(
        _CHART_URL.format(ticker=ticker),
        params={"interval": "1d", "range": range_},
        timeout=8,
    )
    resp.raise_for_status()
    return parse_yahoo_closes(resp.json())
