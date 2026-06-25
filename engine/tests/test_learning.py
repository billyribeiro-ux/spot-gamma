"""Tests for the self-learning layer (panel / dataset / backtest / weights /
calibration / model / store).

All offline and deterministic — synthetic panels and feature rows with *known*
relationships, so we can assert the learner recovers them, respects point-in-time
ordering (no lookahead), and makes the right adopt/reject decisions.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from spotgamma.learning.backtest import (
    prior_composite_fit_predict,
    signal_report,
    spearman,
    walk_forward,
    weighted_roro,
)
from spotgamma.learning.calibration import calibrate
from spotgamma.learning.dataset import FeatureRow, build_dataset, forward_returns_at, signal_scores_at
from spotgamma.learning.model import apply_tilt, calibration_lookup, effective_weights, train_model
from spotgamma.learning.panel import AsOf, Observation, build_panel, coverage, parse_yahoo_daily
from spotgamma.learning.store import load_model, save_model
from spotgamma.learning.weights import calibrate_regime_weights, fit_return_tilt
from spotgamma.marketstructure.composite import WEIGHTS

_BASE = date(2018, 1, 1)


def _d(i: int) -> date:
    return _BASE + timedelta(days=i)


# --- panel -----------------------------------------------------------------
def test_parse_yahoo_daily_drops_nulls_and_sorts():
    day0 = 1_577_836_800  # 2020-01-01 UTC; distinct daily epochs
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [day0 + 2 * 86400, day0, day0 + 86400],
                    "indicators": {"quote": [{"close": [30.0, None, 20.0]}]},
                }
            ]
        }
    }
    obs = parse_yahoo_daily(payload)
    # null (day0) dropped; remaining sorted chronologically by date (day1, day2)
    assert [o.value for o in obs] == [20.0, 30.0]


def test_asof_returns_last_on_or_before():
    a = AsOf([Observation(_d(0), 1.0), Observation(_d(10), 2.0)])
    assert a.at(_d(-1)) is None  # before all data
    assert a.at(_d(0)) == 1.0
    assert a.at(_d(5)) == 1.0  # carries forward last known
    assert a.at(_d(10)) == 2.0
    assert a.at(_d(99)) == 2.0


def test_build_panel_is_point_in_time():
    series = {
        "spy": [Observation(_d(0), 100.0), Observation(_d(1), 101.0), Observation(_d(2), 102.0)],
        # macro publishes only on day 1; day 0 must be None (not yet known)
        "hy_oas": [Observation(_d(1), 3.0)],
    }
    panel = build_panel(series, calendar_key="spy")
    assert [r.date for r in panel] == [_d(0), _d(1), _d(2)]
    assert panel[0].values["hy_oas"] is None  # not known on day 0
    assert panel[1].values["hy_oas"] == 3.0
    assert panel[2].values["hy_oas"] == 3.0  # carried forward
    cov = coverage(panel)
    assert cov["hy_oas"]["n"] == 2 and cov["spy"]["n"] == 3


# --- dataset (no lookahead) ------------------------------------------------
def _flat_panel(n: int, vix=18.0, dxy=100.0):
    from spotgamma.learning.panel import PanelRow

    return [
        PanelRow(
            _d(i),
            {"vix": vix, "vix3m": vix + 2, "vvix": 90.0, "dxy": dxy, "hy_oas": 3.0, "spread": 0.5, "spy": 100.0 + i},
        )
        for i in range(n)
    ]


def test_forward_returns_are_strictly_forward():
    panel = _flat_panel(10)
    fwd = forward_returns_at(panel, 0, (1, 5))
    assert fwd[1] == pytest.approx(101.0 / 100.0 - 1.0)
    assert fwd[5] == pytest.approx(105.0 / 100.0 - 1.0)
    # last row has no future bar -> empty
    assert forward_returns_at(panel, 9, (1,)) == {}


def test_signal_scores_use_only_past_for_trailing_stats():
    from spotgamma.learning.panel import PanelRow

    # DXY jumps on the last row; the 200d MA at an earlier index must NOT see it.
    panel = [
        PanelRow(_d(i), {"vix": 18.0, "vix3m": 20.0, "vvix": 90.0, "dxy": 100.0, "spy": 100.0}) for i in range(250)
    ]
    panel.append(PanelRow(_d(250), {"vix": 18.0, "vix3m": 20.0, "vvix": 90.0, "dxy": 200.0, "spy": 100.0}))
    early = signal_scores_at(panel, 100)
    late = signal_scores_at(panel, 250)
    assert early is not None and late is not None
    # the early dollar score cannot reflect the future spike (different read)
    assert early["dollar"] != late["dollar"]


def test_build_dataset_drops_unlabeled_tail():
    ds = build_dataset(_flat_panel(30), horizons=(5,))
    # rows 0..24 have a +5 label; the last 5 rows do not
    assert len(ds) == 25
    assert all(5 in r.fwd_returns for r in ds)


# --- backtest --------------------------------------------------------------
def test_spearman_known_values():
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_weighted_roro_matches_manual():
    scores = {"vix": 1.0, "credit": -1.0, "yield_curve": 1.0}  # curve is context-only
    expected = (WEIGHTS["vix"] * 1.0 + WEIGHTS["credit"] * -1.0) / (WEIGHTS["vix"] + WEIGHTS["credit"])
    assert weighted_roro(scores) == pytest.approx(expected)


def _contrarian_rows(n=400, horizon=5, slope=-0.5):
    """fwd_return = slope * vix_score + tiny deterministic wobble."""
    rows = []
    for i in range(n):
        s = ((i % 41) / 20.0) - 1.0  # sweep -1..1
        wobble = 0.0005 * (((i * 7) % 5) - 2)
        rows.append(FeatureRow(_d(i).isoformat(), {"vix": s}, {horizon: slope * s + wobble}))
    return rows


def test_signal_ic_recovers_sign():
    # contrarian: high "risk-off" vix score -> lower forward return -> negative IC
    rep = signal_report(_contrarian_rows(slope=-0.5), "vix", 5)
    assert rep.ic < -0.8 and rep.n == 400


def test_walk_forward_has_no_lookahead():
    seen = {"ok": True}

    def checking_fp(train, test, horizon):
        if train and test:
            last_train = max(r.date for r in train)
            first_test = min(r.date for r in test)
            if not (first_test > last_train):
                seen["ok"] = False
        return prior_composite_fit_predict(train, test, horizon)

    rows = [FeatureRow(_d(i).isoformat(), {"vix": ((i % 7) / 3.0 - 1.0)}, {5: 0.001 * (i % 3)}) for i in range(200)]
    walk_forward(rows, 5, checking_fp, n_splits=5)
    assert seen["ok"], "a test block must never precede or overlap its training data"


# --- weights ---------------------------------------------------------------
def test_ridge_tilt_recovers_contrarian_sign():
    tilt = fit_return_tilt(_contrarian_rows(slope=-0.5), 5)
    assert tilt is not None
    vix_idx = tilt.features.index("vix")
    assert tilt.coef[vix_idx] < 0  # learned the contrarian (negative) relationship


def test_ridge_tilt_shrinks_to_mean_with_no_signal():
    # label independent of features -> coefficients shrink toward 0, predict ~ mean
    rows = [FeatureRow(_d(i).isoformat(), {"vix": ((i % 11) / 5.0 - 1.0)}, {5: 0.01}) for i in range(300)]
    tilt = fit_return_tilt(rows, 5)
    assert tilt is not None
    assert tilt.predict({"vix": 1.0}) == pytest.approx(0.01, abs=1e-3)


def test_calibrate_weights_equals_prior_at_lam_zero():
    rows = _contrarian_rows()
    w = calibrate_regime_weights(rows, 5, lam=0.0)
    for k in ("vix", "term_structure", "vvix", "credit", "dollar"):
        assert w[k] == pytest.approx(WEIGHTS[k])


def test_calibrate_weights_preserves_recalibratable_mass():
    rows = _contrarian_rows()
    w = calibrate_regime_weights(rows, 5, lam=1.0)
    recal = ("vix", "term_structure", "vvix", "credit", "dollar")
    prior_mass = sum(WEIGHTS[k] for k in recal)
    assert sum(w[k] for k in recal) == pytest.approx(prior_mass)
    # untouched signals keep their prior
    assert w["breadth"] == WEIGHTS["breadth"] and w["put_call"] == WEIGHTS["put_call"]


# --- calibration -----------------------------------------------------------
def test_calibration_is_monotone_for_monotone_data():
    # score == forward return -> higher buckets have higher mean forward return
    scores = [i / 100.0 for i in range(100)]
    rets = [i / 100.0 for i in range(100)]
    calib = calibrate(scores, rets, horizon=5, n_bins=5)
    means = [b.mean_fwd for b in calib.buckets]
    assert means == sorted(means) and len(calib.buckets) >= 4


def test_calibration_degenerate_inputs_collapse_to_one_bucket():
    calib = calibrate([0.1, 0.1, 0.1, 0.1], [0.0, 0.01, -0.01, 0.0], horizon=5, n_bins=5)
    assert len(calib.buckets) == 1


# --- model + store ---------------------------------------------------------
def test_train_model_artifact_shape_and_gates():
    model = train_model(_contrarian_rows(n=500, slope=-0.5), horizon=5)
    assert model["horizon"] == 5 and model["n_train"] == 500
    v = model["validation"]
    assert set(v) >= {"prior_oos_ic", "calibrated_oos_ic", "tilt_oos_ic", "adopt_weights", "adopt_tilt"}
    # a strong contrarian signal -> the tilt should validate OOS and be adopted
    assert v["adopt_tilt"] is True
    # effective weights == prior unless calibration beat it OOS
    eff = effective_weights(model)
    if not v["adopt_weights"]:
        assert eff == {k: float(x) for k, x in WEIGHTS.items()}


def test_apply_tilt_none_when_not_adopted():
    # flat label -> tilt has no OOS edge -> not adopted -> apply_tilt returns None
    rows = [FeatureRow(_d(i).isoformat(), {"vix": ((i % 13) / 6.0 - 1.0)}, {5: 0.01}) for i in range(400)]
    model = train_model(rows, horizon=5)
    assert model["validation"]["adopt_tilt"] is False
    assert apply_tilt(model, {"vix": 1.0}) is None


def test_calibration_lookup_returns_bucket():
    model = train_model(_contrarian_rows(n=500), horizon=5)
    bucket = calibration_lookup(model, 0.0)
    assert bucket is not None and "mean_fwd" in bucket and bucket["n"] > 0


def test_model_store_round_trip(tmp_path):
    p = tmp_path / "learned_model.json"
    model = train_model(_contrarian_rows(n=300), horizon=5)
    save_model(model, str(p))
    loaded = load_model(str(p))
    assert loaded is not None and loaded["horizon"] == 5
    assert loaded["validation"]["tilt_oos_ic"] == model["validation"]["tilt_oos_ic"]


def test_load_model_missing_or_corrupt_is_none(tmp_path):
    assert load_model(str(tmp_path / "nope.json")) is None
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid")
    assert load_model(str(bad)) is None
