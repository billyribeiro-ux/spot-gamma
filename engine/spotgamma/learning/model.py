"""Train, validate, persist, and apply the learned market-structure model.

Ties the pieces together into one honest artifact:

* **regime weights** — reliability-calibrated, shrunk to the §5 prior
  (``weights.calibrate_regime_weights``);
* **return tilt** — the ridge contrarian overlay (``weights.fit_return_tilt``);
* **calibration** — score → empirical forward-return buckets
  (``calibration.calibrate``);
* **validation** — walk-forward OOS IC for the prior, the calibrated weights, and
  the tilt, plus an **adopt/reject gate**: calibrated weights are adopted only if
  they beat the prior OOS (by |IC|); the tilt is adopted only if its OOS IC clears
  a modest floor. If neither helps, the live read keeps the documented prior.

The whole model trains from the freshly-fetched historical panel, so re-running
``train_model`` is the self-updating loop — each run learns from the latest data
and the artifact records what (if anything) earned adoption.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..marketstructure.composite import WEIGHTS
from .backtest import prior_composite_fit_predict, signal_report, walk_forward, weighted_roro
from .calibration import calibrate
from .dataset import HISTORICAL_SIGNALS, FeatureRow
from .weights import calibrate_regime_weights, fit_return_tilt, tilt_fit_predict

# A learned tilt must clear this OOS IC to be worth surfacing as a directional
# overlay (modest — the macro/vol edge is real but small, see the backtest).
_TILT_ADOPT_MIN_OOS_IC = 0.03


def _calibrated_fit_predict_factory(lam: float):
    """Walk-forward strategy that recalibrates weights on each train block."""

    def fp(train: Sequence[FeatureRow], test: Sequence[FeatureRow], horizon: int):
        w = calibrate_regime_weights(train, horizon, lam=lam)
        return [(weighted_roro(r.scores, w), r.fwd_returns[horizon]) for r in test if horizon in r.fwd_returns]

    return fp


def train_model(
    rows: Sequence[FeatureRow],
    horizon: int = 5,
    *,
    lam: float = 0.5,
    n_bins: int = 5,
    n_splits: int = 5,
) -> dict:
    """Fit + walk-forward-validate the full model; return a serializable artifact."""
    rows = list(rows)
    trained_through = rows[-1].date if rows else None

    # 1. calibrated regime weights (full-sample, for deployment)
    regime_weights = calibrate_regime_weights(rows, horizon, lam=lam)

    # 2. return-tilt model (full-sample, for deployment)
    tilt = fit_return_tilt(rows, horizon)

    # 3. walk-forward OOS validation (no test row ever trained the model scoring it)
    prior_wf = walk_forward(rows, horizon, prior_composite_fit_predict, n_splits=n_splits)
    calib_wf = walk_forward(rows, horizon, _calibrated_fit_predict_factory(lam), n_splits=n_splits)
    tilt_wf = walk_forward(rows, horizon, tilt_fit_predict, n_splits=n_splits)

    def _abs(x: float) -> float:
        return abs(x) if x == x else 0.0  # NaN -> 0

    adopt_weights = _abs(calib_wf.oos_ic) > _abs(prior_wf.oos_ic)
    adopt_tilt = (tilt_wf.oos_ic == tilt_wf.oos_ic) and tilt_wf.oos_ic >= _TILT_ADOPT_MIN_OOS_IC

    # 4. calibrate score -> forward returns on the weights that will be DEPLOYED
    # (calibrated only if adopted, else the prior), so the live bucket lookup is
    # consistent with the live composite score.
    deploy_weights = regime_weights if adopt_weights else dict(WEIGHTS)
    comp_scores = [weighted_roro(r.scores, deploy_weights) for r in rows if horizon in r.fwd_returns]
    comp_rets = [r.fwd_returns[horizon] for r in rows if horizon in r.fwd_returns]
    calib = calibrate(comp_scores, comp_rets, horizon=horizon, n_bins=n_bins)

    per_signal_ic = {k: signal_report(rows, k, horizon).ic for k in HISTORICAL_SIGNALS}

    return {
        "schema": 1,
        "horizon": horizon,
        "trained_through": trained_through,
        "n_train": len(rows),
        "lam": lam,
        "regime_weights": regime_weights,
        "tilt": tilt._asdict() if tilt else None,
        "calibration": {
            "horizon": calib.horizon,
            "buckets": [list(b) for b in calib.buckets],
        },
        "validation": {
            "prior_oos_ic": prior_wf.oos_ic,
            "calibrated_oos_ic": calib_wf.oos_ic,
            "tilt_oos_ic": tilt_wf.oos_ic,
            "n_oos": prior_wf.n,
            "n_splits": prior_wf.n_splits,
            "adopt_weights": adopt_weights,
            "adopt_tilt": adopt_tilt,
        },
        "per_signal_ic": per_signal_ic,
    }


def effective_weights(model: dict | None) -> dict[str, float]:
    """The weights the live read should use: calibrated if adopted, else the prior."""
    if model and model.get("validation", {}).get("adopt_weights") and model.get("regime_weights"):
        return {k: float(v) for k, v in model["regime_weights"].items()}
    return dict(WEIGHTS)


def apply_tilt(model: dict | None, scores: dict[str, float]) -> float | None:
    """Predicted forward return from the adopted tilt for current scores (else None)."""
    if not (model and model.get("validation", {}).get("adopt_tilt") and model.get("tilt")):
        return None
    from .weights import RidgeTilt

    t = RidgeTilt(**model["tilt"])
    return t.predict(scores)


def calibration_lookup(model: dict | None, score: float) -> dict | None:
    """Empirical forward-return bucket for a composite score (else None)."""
    if not (model and model.get("calibration", {}).get("buckets")):
        return None
    for lo, hi, n, mean_fwd, pct_pos in model["calibration"]["buckets"]:
        if lo <= score < hi:
            return {"n": int(n), "mean_fwd": mean_fwd, "pct_positive": pct_pos}
    last = model["calibration"]["buckets"][-1]
    return {"n": int(last[2]), "mean_fwd": last[3], "pct_positive": last[4]}
