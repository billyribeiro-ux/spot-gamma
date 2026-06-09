"""Gap statistics from daily OHLC (§6.1).

Pure functions over OHLC bars — no network. The methodology's load-bearing point:
the "~70% of gaps fill" headline is true *only because most gaps are tiny*; the
fill rate collapses to ~30% for large gaps. So we **always report fill rate
conditioned on size bucket**, never one blended number, and we surface the sample
size per bucket so a thin cell can't masquerade as a statistic.

Use SPY (or ES), not ^GSPC — the SPX cash "open" is a known artifact. The bars
must be split/dividend-adjusted consistently or ex-div days read as phantom gaps.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple


class Bar(NamedTuple):
    open: float
    high: float
    low: float
    close: float


# Size buckets in percent (|gap|), per §6.1. The dead-zone below 0.05% is noise.
_BUCKETS: list[tuple[str, float, float]] = [
    ("0.05-0.25%", 0.0005, 0.0025),
    ("0.25-0.5%", 0.0025, 0.005),
    ("0.5-1%", 0.005, 0.01),
    ("1-2%", 0.01, 0.02),
    (">=2%", 0.02, float("inf")),
]
_DEAD_ZONE = 0.0005  # |gap| below this is rounding noise, not a gap


class GapBucket(NamedTuple):
    bucket: str
    n: int  # sample size ("n" — a field named "count" would shadow tuple.count)
    fill_rate: float | None  # None when the cell is empty
    median_abs_gap_pct: float | None


class GapStats(NamedTuple):
    n_sessions: int  # gaps measured (above the dead zone)
    buckets: list[GapBucket]
    today_gap_pct: float | None  # most recent gap, if computable
    today_bucket: str | None
    today_fill_probability: float | None  # the conditioned rate for today's bucket


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _gap_pct(prev_close: float, open_: float) -> float:
    return open_ / prev_close - 1.0 if prev_close else 0.0


def _filled(prev_close: float, gap_pct: float, bar: Bar) -> bool:
    """Same-day fill from daily OHLC: gap-up fills if low<=prev_close; down if high>=."""
    if gap_pct > 0:
        return bar.low <= prev_close
    return bar.high >= prev_close


def compute_gap_stats(bars: Sequence[Bar]) -> GapStats:
    """Size-bucketed gap-fill statistics over a daily OHLC history (chronological)."""
    # Accumulate per bucket: list of (abs_gap, filled).
    per_bucket: dict[str, list[tuple[float, bool]]] = {b[0]: [] for b in _BUCKETS}
    n = 0
    today_gap = None
    today_bucket = None

    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        gp = _gap_pct(prev_close, bars[i].open)
        if abs(gp) < _DEAD_ZONE:
            continue
        n += 1
        bucket = _bucket_for(abs(gp))
        per_bucket[bucket].append((abs(gp), _filled(prev_close, gp, bars[i])))
        if i == len(bars) - 1:
            today_gap, today_bucket = gp, bucket

    buckets = []
    today_fill = None
    for name, _lo, _hi in _BUCKETS:
        rows = per_bucket[name]
        if rows:
            fill_rate = sum(1 for _, f in rows if f) / len(rows)
            med = _median([g for g, _ in rows])
            buckets.append(GapBucket(name, len(rows), round(fill_rate, 3), round(med * 100, 3)))
            if name == today_bucket:
                today_fill = round(fill_rate, 3)
        else:
            buckets.append(GapBucket(name, 0, None, None))

    return GapStats(
        n_sessions=n,
        buckets=buckets,
        today_gap_pct=round(today_gap * 100, 3) if today_gap is not None else None,
        today_bucket=today_bucket,
        today_fill_probability=today_fill,
    )


def _bucket_for(abs_gap: float) -> str:
    for name, lo, hi in _BUCKETS:
        if lo <= abs_gap < hi:
            return name
    return _BUCKETS[-1][0]
