"""Live data wiring for the §6/§7 extensions.

Connects the pure scoring logic (gaps/breadth/putcall/calendar) to free sources:
- **Gaps** — SPY daily OHLC via the existing Yahoo pipeline (use SPY, not ^GSPC).
- **Breadth** — closes for a liquid constituent universe via Yahoo (one request per
  symbol; we use a curated large-cap set rather than all 500 so a free, no-key
  read stays fast — documented as a pragmatic proxy in MARKET_STRUCTURE §7).
- **Event schedule** — FOMC/CPI/PCE/GDP dates from a maintained JSON file
  (``scheduled_events``), never formula-faked. The file path is configurable; if
  absent, only the deterministic events (OPEX/witching/NFP-heuristic/holidays)
  appear.

All network calls go through the shared retrying session and degrade gracefully.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from .gaps import Bar, GapStats, compute_gap_stats

# A liquid, sector-spread large-cap universe — a pragmatic free proxy for full
# S&P 500 breadth (one Yahoo request each; the full constituent list can be wired
# later). Chosen for liquidity + sector coverage, not stock-picking.
_BREADTH_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "JPM",
    "V",
    "LLY",
    "UNH",
    "XOM",
    "MA",
    "COST",
    "HD",
    "PG",
    "JNJ",
    "ABBV",
    "WMT",
    "MRK",
    "CVX",
    "KO",
    "PEP",
    "ADBE",
    "CRM",
    "BAC",
    "NFLX",
    "AMD",
    "CSCO",
    "ACN",
    "MCD",
    "TMO",
    "ABT",
    "LIN",
    "DIS",
    "WFC",
    "INTC",
    "QCOM",
    "TXN",
    "CAT",
    "GE",
    "VZ",
    "IBM",
    "NOW",
    "PM",
    "UNP",
    "HON",
    "GS",
    "BA",
]


def fetch_spy_bars(timeframe: str = "1D") -> list[Bar]:
    """SPY daily OHLC as gap-ready bars (most recent last)."""
    from ..history import fetch_history

    data = fetch_history("SPY", timeframe)
    return [Bar(b["open"], b["high"], b["low"], b["close"]) for b in data["bars"]]


def live_gap_stats() -> GapStats:
    """Size-conditioned gap-fill stats from live SPY daily history."""
    return compute_gap_stats(fetch_spy_bars("1D"))


def fetch_constituent_closes(symbols: list[str] | None = None) -> dict[str, list[float]]:
    """Daily closes for the breadth universe (per-symbol; skips any that fail)."""
    from ._http_ms import session

    http = session()
    out: dict[str, list[float]] = {}
    for sym in symbols or _BREADTH_UNIVERSE:
        try:
            resp = http.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"interval": "1d", "range": "1y"},
                timeout=20,
            )
            resp.raise_for_status()
            quote = resp.json()["chart"]["result"][0]["indicators"]["quote"][0]
            closes = [c for c in quote.get("close", []) if c is not None]
            if closes:
                out[sym] = closes
        except Exception:
            continue
    return out


def load_scheduled_events(path: str | None = None) -> dict[date, list[str]]:
    """Load the maintained FOMC/CPI/PCE/GDP schedule (never formula-faked).

    JSON shape: ``{"2026-06-17": ["FOMC"], "2026-06-11": ["CPI"], ...}``. Path from
    ``SPOTGAMMA_EVENTS`` env or the default ``instance/events.json``; empty if
    absent (only deterministic events then appear).
    """
    p = Path(path or os.environ.get("SPOTGAMMA_EVENTS", _default_events_path()))
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[date, list[str]] = {}
    for k, v in raw.items():
        try:
            out[date.fromisoformat(k)] = list(v)
        except ValueError:
            continue
    return out


def _default_events_path() -> Path:
    # engine/spotgamma/marketstructure/feeds.py -> repo root / instance / events.json
    return Path(__file__).resolve().parents[3] / "instance" / "events.json"
