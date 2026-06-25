"""Out-of-sample backtest metrics for the market-structure signals.

Answers the ``docs/MARKET_STRUCTURE.md`` §7 open question — *does the composite add
information over the individual signals, and in which direction?* — with honest,
sign-aware statistics:

* **Information coefficient (IC)** — Spearman rank correlation between a signal/
  composite score at *t* and the forward SPY return *t→t+h*. Sign matters: the
  signals are oriented **+1 = risk-off**, so a *negative* IC means the orientation
  predicts returns directly, a *positive* IC means the relationship is contrarian
  (high "risk-off" reading preceded higher returns — the mean-reversion the doc
  flags for VIX). We report the sign, never its absolute value.
* **Tercile means** — mean forward return in the bottom/middle/top third of the
  score, so drift doesn't masquerade as edge (a plain hit-rate is inflated by the
  market's upward drift; conditional means are not).
* **Walk-forward** — expanding-window, out-of-sample evaluation. Every reported
  OOS number comes from a block the model never saw in training.

Pure functions over a dataset (``list[FeatureRow]``); Spearman is implemented in
numpy so the package needs no scipy. Network only enters via ``panel.fetch_panel``
upstream.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NamedTuple

import numpy as np

from ..marketstructure.composite import _CONTEXT_ONLY, WEIGHTS
from .dataset import FeatureRow


def _rank(a: np.ndarray) -> np.ndarray:
    """Average ranks (ties shared), for Spearman correlation."""
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(len(a), dtype=float)
    # average tied ranks
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inv, ranks)
    avg = sums / counts
    return avg[inv]


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    xc, yc = x - x.mean(), y - y.mean()
    denom = float(np.sqrt((xc * xc).sum() * (yc * yc).sum()))
    return float((xc * yc).sum() / denom) if denom > 0 else float("nan")


def spearman(x: Sequence[float] | np.ndarray, y: Sequence[float] | np.ndarray) -> float:
    """Spearman rank correlation (numpy-only). NaN if fewer than 3 points."""
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(xa) < 3:
        return float("nan")
    return _pearson(_rank(xa), _rank(ya))


def weighted_roro(scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Prior-weighted RORO over present signals (mirrors ``composite.compose``).

    Context-only signals (the yield curve) are excluded; weights renormalize over
    whichever signals are present, so a missing feed degrades gracefully.
    """
    w = weights or WEIGHTS
    num = den = 0.0
    for k, v in scores.items():
        if k in _CONTEXT_ONLY:
            continue
        wk = w.get(k, 0.0)
        num += wk * v
        den += wk
    return num / den if den else 0.0


def _aligned(rows: Sequence[FeatureRow], key: str, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for r in rows:
        if key in r.scores and horizon in r.fwd_returns:
            xs.append(r.scores[key])
            ys.append(r.fwd_returns[horizon])
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def _composite_aligned(
    rows: Sequence[FeatureRow], horizon: int, weights: dict[str, float] | None = None
) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for r in rows:
        if horizon in r.fwd_returns:
            xs.append(weighted_roro(r.scores, weights))
            ys.append(r.fwd_returns[horizon])
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


class SignalReport(NamedTuple):
    key: str
    horizon: int
    ic: float  # signed Spearman IC (negative = orientation predicts; positive = contrarian)
    n: int
    tercile_fwd: list[float]  # mean forward return in [bottom, middle, top] score tercile


def _terciles(x: np.ndarray, y: np.ndarray) -> list[float]:
    if len(x) < 6:
        return [float("nan")] * 3
    order = x.argsort()
    thirds = np.array_split(order, 3)
    return [float(y[idx].mean()) for idx in thirds]


def signal_report(rows: Sequence[FeatureRow], key: str, horizon: int) -> SignalReport:
    """IC + tercile-conditional forward returns for one signal at one horizon."""
    x, y = _aligned(rows, key, horizon)
    return SignalReport(key, horizon, spearman(x, y), len(x), _terciles(x, y))


def composite_report(rows: Sequence[FeatureRow], horizon: int, weights: dict[str, float] | None = None) -> SignalReport:
    """IC + terciles for the prior-weighted composite at one horizon."""
    x, y = _composite_aligned(rows, horizon, weights)
    return SignalReport("composite", horizon, spearman(x, y), len(x), _terciles(x, y))


# --- walk-forward (out-of-sample) ------------------------------------------
# fit_predict(train, test, horizon) -> list of (predicted_score, actual_return)
FitPredict = Callable[[Sequence[FeatureRow], Sequence[FeatureRow], int], list[tuple[float, float]]]


class WalkForwardResult(NamedTuple):
    horizon: int
    oos_ic: float  # IC of out-of-sample predictions vs realized returns
    n: int  # number of OOS points
    n_splits: int


def walk_forward(
    rows: Sequence[FeatureRow],
    horizon: int,
    fit_predict: FitPredict,
    *,
    n_splits: int = 5,
    min_train_frac: float = 0.4,
) -> WalkForwardResult:
    """Expanding-window OOS evaluation.

    The first ``min_train_frac`` of the (chronological) rows seed the initial
    training set; the remainder is divided into ``n_splits`` contiguous test
    blocks. For each block the model is fit on everything strictly before it and
    predicts on the block. Predictions are pooled and scored by IC — so no test
    point ever influenced the model that scored it.
    """
    rows = list(rows)
    n = len(rows)
    if n < 20:
        return WalkForwardResult(horizon, float("nan"), 0, 0)
    start = max(int(n * min_train_frac), 10)
    bounds = np.linspace(start, n, n_splits + 1, dtype=int)
    preds: list[float] = []
    actuals: list[float] = []
    used_splits = 0
    for i in range(n_splits):
        a, b = int(bounds[i]), int(bounds[i + 1])
        if b <= a:
            continue
        train, test = rows[:a], rows[a:b]
        for pred, actual in fit_predict(train, test, horizon):
            preds.append(pred)
            actuals.append(actual)
        used_splits += 1
    return WalkForwardResult(horizon, spearman(preds, actuals), len(preds), used_splits)


def prior_composite_fit_predict(
    train: Sequence[FeatureRow], test: Sequence[FeatureRow], horizon: int
) -> list[tuple[float, float]]:
    """Baseline 'model': the documented-prior composite (no fitting at all).

    Used as the walk-forward control — any learned model must beat this OOS to be
    worth adopting.
    """
    out = []
    for r in test:
        if horizon in r.fwd_returns:
            out.append((weighted_roro(r.scores), r.fwd_returns[horizon]))
    return out
