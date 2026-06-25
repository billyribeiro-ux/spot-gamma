"""Empirical calibration of a score into a forward-return distribution.

A composite/tilt score is unitless on its own. Calibration bins historical scores
into quantile buckets and reports, per bucket, the realized forward-return
distribution (mean, share positive, sample size). A new score is then mapped to
the bucket it falls in, so the read becomes *"historically, scores in this range
preceded a mean Xd return of Y% with Z% positive (n=N)"* — an honest,
sample-sized statement, never a manufactured probability.

Pure numpy; bins are computed from training data only (caller passes the training
rows), so applying a calibrator to live data has no lookahead.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import numpy as np


class CalibrationBucket(NamedTuple):
    lo: float  # score lower edge (-inf for the first bucket)
    hi: float  # score upper edge (+inf for the last bucket)
    n: int
    mean_fwd: float  # mean forward return in the bucket
    pct_positive: float  # share with positive forward return (0..1)


class Calibrator(NamedTuple):
    horizon: int
    buckets: list[CalibrationBucket]

    def lookup(self, score: float) -> CalibrationBucket | None:
        """The bucket a score falls in (by its [lo, hi) edges)."""
        for b in self.buckets:
            if b.lo <= score < b.hi:
                return b
        return self.buckets[-1] if self.buckets else None


def calibrate(
    scores: Sequence[float],
    returns: Sequence[float],
    *,
    horizon: int,
    n_bins: int = 5,
) -> Calibrator:
    """Build a quantile-binned calibrator from aligned (score, forward-return).

    Bins are quantile edges over the scores, so each bucket holds ~equal samples.
    Degenerate inputs (few points, all-equal scores) collapse to a single bucket.
    """
    s = np.asarray(scores, dtype=float)
    r = np.asarray(returns, dtype=float)
    if len(s) < n_bins * 2 or float(s.min()) == float(s.max()):
        if len(s) == 0:
            return Calibrator(horizon, [])
        return Calibrator(
            horizon,
            [CalibrationBucket(float("-inf"), float("inf"), len(s), float(r.mean()), float((r > 0).mean()))],
        )
    edges = np.quantile(s, np.linspace(0, 1, n_bins + 1))
    edges = np.unique(edges)  # collapse duplicate quantiles
    buckets: list[CalibrationBucket] = []
    for i in range(len(edges) - 1):
        lo = edges[i]
        hi = edges[i + 1]
        # last bucket is inclusive of the top edge
        mask = (s >= lo) & (s <= hi) if i == len(edges) - 2 else (s >= lo) & (s < hi)
        if not mask.any():
            continue
        rr = r[mask]
        out_lo = float("-inf") if i == 0 else float(lo)
        out_hi = float("inf") if i == len(edges) - 2 else float(hi)
        buckets.append(CalibrationBucket(out_lo, out_hi, int(mask.sum()), float(rr.mean()), float((rr > 0).mean())))
    return Calibrator(horizon, buckets)
