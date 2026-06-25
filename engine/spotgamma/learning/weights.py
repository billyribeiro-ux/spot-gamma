"""The learning core: regime-weight calibration + a ridge return-tilt model.

Two deliberately separate learners, each respecting ``docs/MARKET_STRUCTURE.md``:

1. **Regime-weight calibration** (``calibrate_regime_weights``) — keeps the
   documented **risk-off orientation** of every signal and only adjusts *how much
   to trust each*, in proportion to its measured reliability (|IC|), **shrunk
   toward the §5 prior** by a blend factor ``lam``. ``lam=0`` is exactly the prior;
   ``lam=1`` is pure reliability weighting. The result is a drop-in replacement for
   ``composite.WEIGHTS`` and is only adopted if it beats the prior out-of-sample.

2. **Return-tilt model** (``RidgeTilt``) — a ridge regression of forward return on
   the signal scores. Because the macro/vol signals are *contrarian* at 1–20d
   horizons (high "risk-off" → higher forward return, the mean-reversion the doc
   flags), this learner will recover a contrarian sign. It is therefore a **distinct
   directional overlay**, never merged into the regime score: the regime read still
   describes the *state*; the tilt is an explicitly-labeled, OOS-validated estimate
   of the forward *return*. Ridge shrinks coefficients toward zero, so with no real
   signal the tilt collapses to the unconditional mean.

numpy-only; no scipy. The fit is closed-form on standardized features.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import numpy as np

from ..marketstructure.composite import _CONTEXT_ONLY, WEIGHTS
from .backtest import signal_report
from .dataset import FeatureRow

# Feature set for the tilt model — the signals with clean free history. Missing
# values (e.g. credit before its history starts) are imputed as 0.0 = neutral, so
# a column simply doesn't contribute on rows where its feed is absent.
TILT_FEATURES = ("vix", "term_structure", "vvix", "credit", "dollar")

# Signals whose weight we can recalibrate from history (have an IC). Breadth,
# put/call, gamma sign and the context-only curve are left at their prior.
_RECALIBRATABLE = ("vix", "term_structure", "vvix", "credit", "dollar")

_DEFAULT_RIDGE_ALPHA = 1.0


class RidgeTilt(NamedTuple):
    features: tuple[str, ...]
    coef: list[float]  # in standardized-feature space
    intercept: float  # unconditional mean forward return
    mu: list[float]  # train feature means (for standardizing at predict time)
    sigma: list[float]  # train feature stds
    alpha: float
    horizon: int

    def predict(self, scores: dict[str, float]) -> float:
        """Predicted forward return for a score dict (missing features -> neutral 0)."""
        z = []
        for j, f in enumerate(self.features):
            v = scores.get(f, 0.0)
            s = self.sigma[j] if self.sigma[j] > 0 else 1.0
            z.append((v - self.mu[j]) / s)
        return float(self.intercept + np.dot(self.coef, z))


def _matrix(rows: Sequence[FeatureRow], features: tuple[str, ...], horizon: int) -> tuple[np.ndarray, np.ndarray]:
    """Feature matrix X and label vector y for rows with the horizon label present.

    Missing feature values are imputed as 0.0 (neutral score)."""
    xs, ys = [], []
    for r in rows:
        if horizon not in r.fwd_returns:
            continue
        xs.append([r.scores.get(f, 0.0) for f in features])
        ys.append(r.fwd_returns[horizon])
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def fit_return_tilt(
    rows: Sequence[FeatureRow],
    horizon: int,
    *,
    alpha: float = _DEFAULT_RIDGE_ALPHA,
    features: tuple[str, ...] = TILT_FEATURES,
) -> RidgeTilt | None:
    """Fit a ridge return-tilt model on standardized features (closed-form)."""
    x, y = _matrix(rows, features, horizon)
    if len(y) < max(20, 4 * len(features)):
        return None
    mu = x.mean(axis=0)
    sigma = x.std(axis=0)
    safe_sigma = np.where(sigma > 0, sigma, 1.0)
    z = (x - mu) / safe_sigma
    intercept = float(y.mean())
    yc = y - intercept
    p = z.shape[1]
    # ridge closed form: (ZᵀZ + αI)⁻¹ Zᵀ yc
    coef = np.linalg.solve(z.T @ z + alpha * np.eye(p), z.T @ yc)
    return RidgeTilt(
        features=tuple(features),
        coef=[float(c) for c in coef],
        intercept=intercept,
        mu=[float(m) for m in mu],
        sigma=[float(s) for s in sigma],
        alpha=alpha,
        horizon=horizon,
    )


def tilt_fit_predict(
    train: Sequence[FeatureRow], test: Sequence[FeatureRow], horizon: int
) -> list[tuple[float, float]]:
    """Walk-forward adapter: fit a tilt on train, predict on test."""
    model = fit_return_tilt(train, horizon)
    if model is None:
        return []
    out = []
    for r in test:
        if horizon in r.fwd_returns:
            out.append((model.predict(r.scores), r.fwd_returns[horizon]))
    return out


def calibrate_regime_weights(
    rows: Sequence[FeatureRow],
    horizon: int,
    *,
    prior: dict[str, float] | None = None,
    lam: float = 0.5,
) -> dict[str, float]:
    """Reliability-weighted regime weights, shrunk toward the documented prior.

    For each recalibratable signal, reliability = |IC| over ``rows``. The learned
    weights among those signals are scaled to preserve their **combined** prior
    mass (so breadth/put-call/gamma balance is untouched), then blended with the
    prior by ``lam``. Orientation is never changed — only relative trust.
    """
    prior = dict(prior or WEIGHTS)
    lam = max(0.0, min(1.0, lam))
    recal = [k for k in _RECALIBRATABLE if k not in _CONTEXT_ONLY]
    rel = {k: abs(signal_report(rows, k, horizon).ic) for k in recal}
    rel = {k: (v if v == v else 0.0) for k, v in rel.items()}  # NaN -> 0
    rel_sum = sum(rel.values())
    prior_mass = sum(prior.get(k, 0.0) for k in recal)
    out = dict(prior)
    if rel_sum > 0 and prior_mass > 0:
        for k in recal:
            learned_k = prior_mass * rel[k] / rel_sum  # preserve combined mass
            out[k] = (1.0 - lam) * prior.get(k, 0.0) + lam * learned_k
    return out


def oos_ic(rows: Sequence[FeatureRow], horizon: int, fit_predict, **kw) -> float:
    """Convenience: walk-forward OOS IC for a fit_predict strategy."""
    from .backtest import walk_forward

    return walk_forward(rows, horizon, fit_predict, **kw).oos_ic
