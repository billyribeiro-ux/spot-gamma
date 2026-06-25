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

import contextlib
import json
import os
import tempfile
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
        # One symbol failing must not sink breadth — documented graceful degradation.
        except Exception:  # nosec B112
            continue
    return out


# A small basket of the most option-liquid names — two broad-market ETFs plus a
# few mega-cap single-names — to approximate an *equity* put/call from chain
# volumes (the clean free P/C feed is gone; see putcall.py). Not stock-picking:
# chosen for option liquidity so the summed volumes are meaningful.
_PUTCALL_UNIVERSE = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA"]


def _yahoo_options_crumb(http) -> str:
    """Fetch a Yahoo cookie + crumb pair (the options endpoint 401s without it)."""
    http.get("https://fc.yahoo.com", timeout=20)  # sets the A3 consent cookie
    resp = http.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=20)
    resp.raise_for_status()
    return resp.text.strip()


def _sum_chain_volumes(result: dict) -> tuple[float, float]:
    """Sum (put_volume, call_volume) from one ``optionChain.result[0]`` payload.

    Pure parser over Yahoo's option-chain JSON shape: ``result["options"]`` is a
    list of expiration blocks, each with ``calls``/``puts`` arrays whose entries
    carry a ``volume`` field (missing/None treated as 0). Sums every expiration
    block present in the payload.
    """
    put_vol = call_vol = 0.0
    for block in result.get("options", []):
        put_vol += sum((c.get("volume") or 0) for c in block.get("puts", []))
        call_vol += sum((c.get("volume") or 0) for c in block.get("calls", []))
    return put_vol, call_vol


def fetch_put_call_volumes(symbols: list[str] | None = None, n_expirations: int = 2) -> tuple[float, float]:
    """Summed (put_volume, call_volume) across a liquid basket's front expirations.

    A free equity-put/call *proxy* from Yahoo's option-chain volumes (the clean
    feed is gone — see putcall.py). For each symbol we sum put vs call ``volume``
    over the front ``n_expirations`` (the front block ships with the base request;
    additional ones are pulled via ``?date=<epoch>``). Symbols that fail are
    skipped. Yahoo's options endpoint needs a browser UA *and* a cookie+crumb.
    """
    from ._http_ms import session

    http = session()
    crumb = _yahoo_options_crumb(http)
    base = "https://query1.finance.yahoo.com/v7/finance/options/"
    total_put = total_call = 0.0
    for sym in symbols or _PUTCALL_UNIVERSE:
        try:
            resp = http.get(base + sym, params={"crumb": crumb}, timeout=20)
            resp.raise_for_status()
            result = resp.json()["optionChain"]["result"][0]
            put_vol, call_vol = _sum_chain_volumes(result)
            for epoch in result.get("expirationDates", [])[1:n_expirations]:
                r2 = http.get(base + sym, params={"crumb": crumb, "date": epoch}, timeout=20)
                r2.raise_for_status()
                p2, c2 = _sum_chain_volumes(r2.json()["optionChain"]["result"][0])
                put_vol += p2
                call_vol += c2
            total_put += put_vol
            total_call += call_vol
        # One symbol failing must not sink the P/C proxy — documented degradation.
        except Exception:  # nosec B112
            continue
    return total_put, total_call


def update_put_call_history(
    ratio: float, today: date | None = None, window: int = 252, path: str | None = None
) -> list[float]:
    """Append today's P/C ratio to the rolling history and return the trailing window.

    Persists a small ``{date: ratio}`` JSON map under ``instance/`` (gitignored),
    deduped by date (today overwrites a prior same-day write). Atomic write +
    tolerant read (a missing/corrupt file starts fresh) following ``api/store.py``.
    Returns the chronological ratios in the trailing ``window`` for z-scoring.
    """
    p = Path(path) if path else Path(os.environ.get("SPOTGAMMA_PUTCALL") or _default_putcall_path())
    day = (today or date.today()).isoformat()

    hist = _read_put_call_history(p)
    hist[day] = ratio
    _write_put_call_history(p, hist)

    ordered = [hist[k] for k in sorted(hist)]
    return ordered[-window:]


def put_call_baseline(today: date | None = None, window: int = 252, path: str | None = None) -> list[float]:
    """Trailing P/C history **excluding** ``today`` — the baseline to z-score
    today's ratio against without self-reference.

    A new observation must not be z-scored against a window that already contains
    it (that shrinks its own z and biases the percentile). This read-only helper
    returns the prior trailing window; persistence stays in
    :func:`update_put_call_history`.
    """
    p = Path(path) if path else Path(os.environ.get("SPOTGAMMA_PUTCALL") or _default_putcall_path())
    day = (today or date.today()).isoformat()
    hist = _read_put_call_history(p)
    ordered = [hist[k] for k in sorted(hist) if k != day]
    return ordered[-window:]


def _read_put_call_history(p: Path) -> dict[str, float]:
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        with contextlib.suppress(TypeError, ValueError):
            out[str(k)] = float(v)
    return out


def _write_put_call_history(p: Path, hist: dict[str, float]) -> None:
    """Atomically persist the P/C history (temp file + ``os.replace``)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".putcall-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(hist, f, indent=2, sort_keys=True)
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _default_putcall_path() -> Path:
    # engine/spotgamma/marketstructure/feeds.py -> repo root / instance / putcall_history.json
    return Path(__file__).resolve().parents[3] / "instance" / "putcall_history.json"


def load_scheduled_events(path: str | None = None) -> dict[date, list[str]]:
    """Load the maintained FOMC/CPI/PCE/GDP schedule (never formula-faked).

    JSON shape: ``{"2026-06-17": ["FOMC"], "2026-06-10": ["CPI"], ...}``. Resolution
    order: explicit ``path`` > ``SPOTGAMMA_EVENTS`` env > user-maintained
    ``instance/events.json`` > the committed ``events.example.json`` (verified
    seed dates). All are feed-required, never inferred from a formula (§6.3).
    """
    candidates = [path or os.environ.get("SPOTGAMMA_EVENTS"), _default_events_path(), _example_events_path()]
    for cand in candidates:
        if not cand:
            continue
        p = Path(cand)
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        out: dict[date, list[str]] = {}
        for k, v in raw.items():
            if k.startswith("_"):  # skip the _comment metadata key
                continue
            try:
                out[date.fromisoformat(k)] = list(v)
            except (ValueError, TypeError):
                continue
        return out
    return {}


def _default_events_path() -> Path:
    # engine/spotgamma/marketstructure/feeds.py -> repo root / instance / events.json
    return Path(__file__).resolve().parents[3] / "instance" / "events.json"


def _example_events_path() -> Path:
    return Path(__file__).resolve().parent / "events.example.json"
