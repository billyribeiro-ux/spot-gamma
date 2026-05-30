"""Put/call sentiment (§7 extension) — z-scored, never absolute thresholds.

The clean free equity put/call feed is gone (FRED's series ended 2019; CBOE's
JSON 403s us), so per the methodology we build a proxy from option-chain volumes
and **threshold by rolling percentile / z-score** — the absolute 0.6/1.0 cutoffs
have drifted with the retail-call boom, so a fixed level is a trap.

The scoring is pure here; the live volume fetch (summing put vs call volume from
option chains we already pull) is the deferred data step.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from .signals import Signal, _clamp


class PutCallStats(NamedTuple):
    ratio: float  # today's put/call volume ratio
    z: float | None  # z-score vs the trailing window (None if too little history)
    percentile: float | None  # 0-100 within the window


def put_call_proxy(put_volume: float, call_volume: float) -> float | None:
    """Put/call volume ratio from summed chain volumes. None if no calls."""
    if call_volume <= 0:
        return None
    return put_volume / call_volume


def zscore(value: float, history: Sequence[float]) -> tuple[float | None, float | None]:
    """(z-score, percentile 0-100) of ``value`` within ``history``. Needs >=20 obs."""
    if len(history) < 20:
        return None, None
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / len(history)
    std = var**0.5
    z = (value - mean) / std if std > 0 else 0.0
    pct = 100.0 * sum(1 for x in history if x <= value) / len(history)
    return z, pct


def put_call_signal(stats: PutCallStats) -> Signal:
    """Put/call -> [-1,+1] contrarian sentiment score (+1 = risk-off).

    Contrarian by construction: a HIGH put/call (fear/capitulation) is washed-out
    positioning -> mildly risk-ON-supportive forward; a LOW put/call (greed/
    complacency) raises downside fragility -> risk-OFF. We score the z-score so the
    drifting absolute baseline doesn't mislead (per §7). Kept modest (sentiment is
    noisier than breadth/credit).

    NOTE the sign: high fear -> negative score (risk-on contrarian); complacency ->
    positive (risk-off). When no z-score is available we abstain (score 0).
    """
    if stats.z is None:
        return Signal("put_call", "n/a", stats.ratio, 0.0, f"P/C {stats.ratio:.2f} (insufficient history)")
    # contrarian: high z (lots of puts = fear) -> risk-on (negative); cap at +-0.6
    score = _clamp(-stats.z / 3.0, -0.6, 0.6)  # z=+1.8 (extreme fear) -> -0.6
    if stats.z >= 1.0:
        label = "fearful"
    elif stats.z <= -1.0:
        label = "complacent"
    else:
        label = "neutral"
    pctl = f", {stats.percentile:.0f}th pct" if stats.percentile is not None else ""
    detail = f"P/C {stats.ratio:.2f} (z {stats.z:+.1f}{pctl}) — {label}"
    return Signal("put_call", label, stats.ratio, round(score, 3), detail)
