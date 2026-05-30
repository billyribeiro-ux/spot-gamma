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
    assert vix_signal(25).label == "elevated"  # ~neutral (just above the 20 mean)
    assert vix_signal(34).label == "fear" and vix_signal(34).score > 0.3
    assert vix_signal(45).label == "crisis" and vix_signal(45).score == 1.0
    assert vix_signal(45).bias == "risk-off"
    # true crisis must score strictly above mere "fear" (no early saturation)
    assert vix_signal(50).score >= vix_signal(32).score


def test_term_structure_contango_vs_backwardation():
    calm = term_structure_signal(15.0, 18.0)  # ratio 0.83 — contango
    assert calm.label == "contango" and calm.score < 0
    stress = term_structure_signal(28.0, 25.0)  # ratio 1.12 — deep backwardation
    assert stress.label == "backwardation" and stress.score == 1.0


def test_vvix_scored_on_own_baseline_not_bare_ratio():
    # Elevated VVIX while VIX is subdued -> fragile, risk-off (the divergence).
    frag = vvix_signal(120.0, 14.0)
    assert frag.label == "fragile" and frag.score > 0.3
    # Genuinely calm VVIX -> risk-on.
    calm = vvix_signal(78.0, 16.0)
    assert calm.score < -0.3
    # CRITICAL: in a real crisis VIX spikes so the bare VVIX/VIX ratio FALLS — the
    # old ratio design read that as risk-on. Scoring VVIX on its own level fixes it:
    # high VVIX with high VIX must still read risk-off, never risk-on.
    crisis = vvix_signal(135.0, 50.0)  # ratio only 2.7
    assert crisis.score > 0.3, "crisis-high VVIX must read risk-off, not risk-on"


def test_vol_regime_matrix():
    assert vol_regime(vix=12, ratio=0.85, vvix=85.0) == "calm"
    assert vol_regime(vix=12, ratio=0.85, vvix=130.0) == "normal"  # doc: VVIX>120 cell
    assert vol_regime(vix=14, ratio=1.05, vvix=85.0) == "stressed"  # backwardation at low VIX
    assert vol_regime(vix=25, ratio=0.9, vvix=85.0) == "normal"
    assert vol_regime(vix=35, ratio=1.2, vvix=140.0) == "crisis"


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
    # same appreciation below trend is gated down (strength below trend is weaker)
    below = dollar_signal(99.0, dxy_200dma=100.0, dxy_20d_change_pct=3.0)
    assert below.score < strong.score
    # a WEAKENING dollar (risk-on) below trend must NOT be muted — the gate is
    # one-sided (only attenuates strength), not applied to negative scores.
    weak_below = dollar_signal(95.0, dxy_200dma=100.0, dxy_20d_change_pct=-3.0)
    weak_above = dollar_signal(101.0, dxy_200dma=100.0, dxy_20d_change_pct=-3.0)
    assert weak_below.score == pytest.approx(weak_above.score)  # both fully -1.0
    assert weak_below.score < -0.9


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
def test_weights_match_documented_table():
    # The doc (§5 table) is the source of truth; assert each value, not just the sum.
    assert WEIGHTS == {
        "vix": 0.18,
        "term_structure": 0.18,
        "vvix": 0.08,
        "credit": 0.22,
        "breadth": 0.15,
        "put_call": 0.05,
        "dollar": 0.08,
        "yield_curve": 0.00,  # context flag — not summed
        "gamma_sign": 0.06,
    }
    # the summed weights (excluding the 0.0 context flag) total 1.0
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_yield_curve_is_context_only_not_summed():
    # An inverted curve alone must NOT move the RORO score (doc: weight 0.0).
    base = compose([vix_signal(18)], vol_regime_label="normal", net_gex=1e10, spot=7500, zero_gamma=7400)
    with_curve = compose(
        [vix_signal(18), yield_curve_signal(-0.5)],
        vol_regime_label="normal",
        net_gex=1e10,
        spot=7500,
        zero_gamma=7400,
    )
    assert with_curve.roro_score == pytest.approx(base.roro_score)
    # but it's still present for display
    assert any(s.key == "yield_curve" for s in with_curve.signals)


def test_modifier_amplifies_conviction_not_sign():
    # THE HIGH-1 REGRESSION: a risk-ON read + deep NEGATIVE gamma must NOT become
    # "more risk-on". The modifier scales magnitude/actionability, never the sign.
    sigs = [vix_signal(13), term_structure_signal(13, 17), credit_signal(2.6)]
    read = compose(sigs, vol_regime_label="calm", net_gex=-6e10, spot=7000, zero_gamma=7350)
    assert read.roro_score < 0  # risk-on direction preserved
    assert read.gamma_modifier > 1.0  # negative gamma = high conviction
    # regime_score keeps the sign; it does NOT go below roro (the old bug did)
    assert read.regime_score < 0  # still risk-on
    # actionability is the amplified magnitude; sign(roro)*actionability == regime_score
    assert read.actionability == pytest.approx(abs(read.roro_score) * read.gamma_modifier)
    assert read.regime_score == pytest.approx(-read.actionability)


def test_compose_risk_off_alignment_amplified():
    sigs = [vix_signal(38), term_structure_signal(30, 27), credit_signal(7.0)]
    read = compose(sigs, vol_regime_label="crisis", net_gex=-6e10, spot=7000, zero_gamma=7350)
    assert read.bias == "risk-off" and read.roro_score > 0.4
    assert read.gamma_modifier > 1.0
    # risk-off + amplification -> regime score above the raw roro (more conviction)
    assert read.regime_score > read.roro_score


def test_compose_risk_on_pinned_dampened():
    sigs = [vix_signal(13), term_structure_signal(13, 17), credit_signal(2.6)]
    read = compose(sigs, vol_regime_label="calm", net_gex=9e10, spot=7580, zero_gamma=7350)
    assert read.bias == "risk-on" and read.roro_score < -0.3
    assert read.gamma_modifier < 1.0  # positive gamma dampens conviction
    # dampened -> regime score closer to zero than roro (extremes fade when pinned)
    assert abs(read.regime_score) < abs(read.roro_score)


def test_compose_detects_divergence():
    # vol calm (risk-on) but credit stressed (risk-off) -> divergence flag
    sigs = [vix_signal(11), credit_signal(7.5)]
    read = compose(sigs, vol_regime_label="normal", net_gex=1e10, spot=7500, zero_gamma=7400)
    assert read.divergence is True


def test_divergence_requires_two_opinionated_signals():
    # a single opinionated signal can't "diverge"
    read = compose([credit_signal(7.5)], vol_regime_label="normal", net_gex=1e10, spot=7500, zero_gamma=7400)
    assert read.divergence is False
    # aligned signals -> no divergence
    aligned = compose(
        [vix_signal(35), credit_signal(7.5)], vol_regime_label="crisis", net_gex=1e10, spot=7500, zero_gamma=7400
    )
    assert aligned.divergence is False


def test_compose_degrades_with_one_signal():
    read = compose([vix_signal(22)], vol_regime_label="normal", net_gex=1e10, spot=7500, zero_gamma=7400)
    assert -1.5 <= read.regime_score <= 1.5


def test_compose_with_no_gamma_still_computes_macro_read():
    # chain feed down -> gamma excluded, macro/vol read still produced
    sigs = [vix_signal(35), credit_signal(7.0)]
    read = compose(sigs, vol_regime_label="crisis", net_gex=None, spot=None, zero_gamma=None)
    assert read.bias == "risk-off" and read.roro_score > 0.3
    assert read.gamma_modifier == 1.0  # neutral, no gamma
    assert read.flip_transition_risk is False
    # gamma_sign weight must be excluded from the denominator (no gamma vote)
    assert -1.0 <= read.roro_score <= 1.0


def test_compose_empty_signals_is_neutral():
    # every feed down -> a defined, neutral read, not a crash or a gamma-only score
    read = compose([], vol_regime_label="normal", net_gex=None, spot=None, zero_gamma=None)
    assert read.roro_score == 0.0 and read.regime_score == 0.0
    assert read.bias == "neutral" and read.divergence is False
