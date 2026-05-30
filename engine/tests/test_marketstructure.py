"""Market-structure layer: pure parsers, signal scoring, and the composite.

No network — every test feeds synthetic data shaped like the real responses.
Thresholds asserted here trace to docs/MARKET_STRUCTURE.md.
"""

from datetime import date

import pytest
from spotgamma.marketstructure.composite import WEIGHTS, compose
from spotgamma.marketstructure.fred import parse_fred_csv
from spotgamma.marketstructure.quotes import parse_yahoo_quote
from spotgamma.marketstructure.signals import (
    credit_signal,
    dollar_signal,
    gamma_modifier,
    term_structure_signal,
    vix_signal,
    vol_regime,
    vvix_signal,
    yield_curve_signal,
)


# --- parsers ---------------------------------------------------------------
def test_parse_fred_csv_skips_missing():
    csv = "observation_date,DGS10\n2026-05-26,4.40\n2026-05-27,.\n2026-05-28,4.45\n"
    pts = parse_fred_csv(csv)
    assert len(pts) == 2  # the "." row is dropped
    assert pts[0] == (date(2026, 5, 26), 4.40)
    assert pts[-1].value == 4.45


def test_parse_yahoo_quote():
    payload = {
        "chart": {"result": [{"meta": {"symbol": "^VIX", "regularMarketPrice": 15.32, "chartPreviousClose": 16.59}}]}
    }
    q = parse_yahoo_quote(payload)
    assert q.symbol == "^VIX" and q.price == 15.32
    assert q.change is not None and q.change < 0
    assert q.change_pct is not None and q.change_pct < 0


def test_parse_yahoo_quote_errors_on_empty():
    with pytest.raises(ValueError):
        parse_yahoo_quote({"chart": {"result": None, "error": {"code": "Not Found"}}})


# --- volatility signals ----------------------------------------------------
def test_vix_signal_bands():
    assert vix_signal(12).label == "calm" and vix_signal(12).score < 0
    assert vix_signal(18).label == "normal"
    assert vix_signal(25).label == "elevated" and vix_signal(25).score > 0
    assert vix_signal(45).label == "crisis" and vix_signal(45).score == 1.0
    assert vix_signal(45).bias == "risk-off"


def test_term_structure_contango_vs_backwardation():
    calm = term_structure_signal(15.0, 18.0)  # ratio 0.83 — contango
    assert calm.label == "contango" and calm.score < 0
    stress = term_structure_signal(28.0, 25.0)  # ratio 1.12 — deep backwardation
    assert stress.label == "backwardation" and stress.score == 1.0


def test_vvix_divergence():
    # low VIX but high VVIX -> fragile, risk-off even though VIX looks calm
    frag = vvix_signal(120.0, 14.0)  # ratio ~8.6
    assert frag.label == "fragile" and frag.score > 0.5
    stable = vvix_signal(80.0, 20.0)  # ratio 4.0
    assert stable.score <= -0.9


def test_vol_regime_matrix():
    assert vol_regime(vix=12, ratio=0.85, vvix_ratio=5.0) == "calm"
    assert vol_regime(vix=14, ratio=1.05, vvix_ratio=5.0) == "stressed"  # backwardation at low VIX
    assert vol_regime(vix=25, ratio=0.9, vvix_ratio=5.0) == "normal"
    assert vol_regime(vix=35, ratio=1.2, vvix_ratio=8.0) == "crisis"


# --- macro signals ---------------------------------------------------------
def test_yield_curve_inversion():
    assert yield_curve_signal(-0.3).label == "inverted" and yield_curve_signal(-0.3).score > 0
    assert yield_curve_signal(2.0).label == "steep" and yield_curve_signal(2.0).score < 0


def test_credit_level_and_rate_of_change():
    tight = credit_signal(2.7)
    assert tight.label == "tight" and tight.score < 0
    stress = credit_signal(7.0)
    assert stress.label == "stress" and stress.score > 0
    # fast widening off a low base nudges risk-off vs a static low level
    widening = credit_signal(3.5, hy_oas_20d_ago=2.7)
    static = credit_signal(3.5)
    assert widening.score > static.score


def test_dollar_smile_low_weight_and_trend_gate():
    # fast appreciation above the 200-DMA -> mild risk-off
    strong = dollar_signal(105.0, dxy_200dma=100.0, dxy_20d_change_pct=3.0)
    assert strong.score > 0.5
    # same appreciation below trend is gated down
    below = dollar_signal(99.0, dxy_200dma=100.0, dxy_20d_change_pct=3.0)
    assert below.score < strong.score


# --- gamma gate ------------------------------------------------------------
def test_gamma_modifier_range():
    # deep positive gamma (spot well above flip) -> dampen toward 0.5
    pos = gamma_modifier(net_gex=9e10, spot=7580, zero_gamma=7350)
    assert 0.5 <= pos < 0.7
    # deep negative gamma -> amplify toward 1.5
    neg = gamma_modifier(net_gex=-5e10, spot=7000, zero_gamma=7350)
    assert 1.3 < neg <= 1.5
    # near the flip -> ~1.0
    near = gamma_modifier(net_gex=1e9, spot=7350, zero_gamma=7350)
    assert 0.9 < near < 1.1


# --- composite -------------------------------------------------------------
def test_weights_documented_and_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_compose_risk_off_alignment():
    # everything aligned risk-off + negative gamma -> strong risk-off, amplified
    sigs = [
        vix_signal(34),
        term_structure_signal(30, 27),  # backwardation
        credit_signal(7.0),
    ]
    read = compose(sigs, vol_regime_label="crisis", net_gex=-6e10, spot=7000, zero_gamma=7350)
    assert read.bias == "risk-off" and read.roro_score > 0.4
    assert read.gamma_modifier > 1.0  # negative gamma amplifies
    assert read.regime_score > read.roro_score  # modifier > 1 pushes it further


def test_compose_risk_on_pinned():
    sigs = [
        vix_signal(13),
        term_structure_signal(13, 17),  # contango
        credit_signal(2.6),
    ]
    read = compose(sigs, vol_regime_label="calm", net_gex=9e10, spot=7580, zero_gamma=7350)
    assert read.bias == "risk-on" and read.roro_score < -0.3
    assert read.gamma_modifier < 1.0  # positive gamma dampens


def test_compose_detects_divergence():
    # vol calm (risk-on) but credit stressed (risk-off) -> divergence flag
    sigs = [vix_signal(12), credit_signal(7.5)]
    read = compose(sigs, vol_regime_label="normal", net_gex=1e10, spot=7500, zero_gamma=7400)
    assert read.divergence is True


def test_compose_degrades_with_missing_signals():
    # only one signal present — still produces a bounded score
    read = compose([vix_signal(22)], vol_regime_label="normal", net_gex=1e10, spot=7500, zero_gamma=7400)
    assert -1.5 <= read.regime_score <= 1.5
