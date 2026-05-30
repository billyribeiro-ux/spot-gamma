"""Market breadth from constituent closes (§7 extension).

No clean free breadth *index* exists (StockCharts/Barchart gate them, Yahoo
doesn't carry the $SPXA50R symbols), so per the methodology we **self-compute**
from constituent daily closes — the highest-value missing signal. The scoring
logic is pure and tested here; wiring the live constituent fetch is a separate
data step (the engine already has a Yahoo OHLC pipeline).

Signals computed: % of constituents above their 50-DMA and 200-DMA, plus a
constituent advance/decline read. Thresholds (§ breadth research): >70% healthy,
<30% washed out for the 50-DMA; >60% / <40% for the 200-DMA.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from .signals import Signal, _clamp, _lerp_score


class BreadthRead(NamedTuple):
    pct_above_50dma: float | None  # 0-100
    pct_above_200dma: float | None
    advancers_pct: float | None  # share of names up on the day
    n_constituents: int


def _sma(closes: Sequence[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def compute_breadth(constituent_closes: dict[str, Sequence[float]]) -> BreadthRead:
    """% above 50/200-DMA and advancers from per-symbol close histories (chronological).

    Each value is the fraction of constituents with enough history that meet the
    condition; symbols with insufficient history are excluded from that metric's
    denominator (not counted as below).
    """
    above50 = total50 = 0
    above200 = total200 = 0
    advancers = total_adv = 0
    n = 0
    for closes in constituent_closes.values():
        if not closes:
            continue
        n += 1
        last = closes[-1]
        s50 = _sma(closes, 50)
        if s50 is not None:
            total50 += 1
            above50 += last > s50
        s200 = _sma(closes, 200)
        if s200 is not None:
            total200 += 1
            above200 += last > s200
        if len(closes) >= 2:
            total_adv += 1
            advancers += last > closes[-2]

    return BreadthRead(
        pct_above_50dma=round(100 * above50 / total50, 1) if total50 else None,
        pct_above_200dma=round(100 * above200 / total200, 1) if total200 else None,
        advancers_pct=round(100 * advancers / total_adv, 1) if total_adv else None,
        n_constituents=n,
    )


def breadth_signal(b: BreadthRead) -> Signal | None:
    """Breadth -> [-1,+1] regime score (+1 = risk-off). None if no data.

    Combines the 200-DMA (secular, weighted higher) and 50-DMA (mid-term) shares.
    High participation = risk-on (-); washed-out = risk-off (+). Thresholds per the
    breadth research: 50-DMA >70 healthy / <30 washed; 200-DMA >60 / <40.
    """
    parts: list[float] = []
    if b.pct_above_200dma is not None:
        # 70% -> -1 (broad health), 25% -> +1 (washed out)
        parts.append(2.0 * _lerp_score(b.pct_above_200dma, calm=70.0, crisis=25.0))
    if b.pct_above_50dma is not None:
        parts.append(_lerp_score(b.pct_above_50dma, calm=75.0, crisis=25.0))
    if not parts:
        return None
    score = _clamp(sum(parts) / (2.0 if len(parts) == 2 else 1.0))
    pa200 = b.pct_above_200dma
    if pa200 is None:
        label = "mixed"
    elif pa200 >= 60:
        label = "broad"
    elif pa200 < 40:
        label = "narrow"
    else:
        label = "mixed"
    detail = f"{pa200:.0f}% > 200DMA — {label}" if pa200 is not None else f"breadth {label}"
    return Signal("breadth", label, pa200 or 0.0, round(score, 3), detail)
