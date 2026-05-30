"""End-to-end level computation on the sample fixtures."""
import pytest

from spotgamma.export_thinkscript import render_thinkscript
from spotgamma.levels import compute_levels
from spotgamma.sources.sample import SampleSource

# Designed wall offsets in tools/make_fixtures.py (call wall above, put wall below).
EXPECTED = {
    "SPX": {"spot": 5850.0, "call_wall": 6000.0, "put_wall": 5700.0},
    "NDX": {"spot": 20500.0, "call_wall": 21100.0, "put_wall": 19900.0},
    "SPY": {"spot": 585.0, "call_wall": 600.0, "put_wall": 570.0},
    "QQQ": {"spot": 498.0, "call_wall": 510.5, "put_wall": 488.0},
}


@pytest.mark.parametrize("symbol", list(EXPECTED))
def test_levels_match_designed_structure(symbol):
    levels = compute_levels(SampleSource().get_chain(symbol))
    exp = EXPECTED[symbol]

    assert levels.spot == exp["spot"]
    assert levels.regime == "positive"  # fixtures put spot above the flip
    assert levels.net_gex > 0

    # walls land at the engineered OI concentrations, on the correct side of spot
    assert levels.call_wall == exp["call_wall"] and levels.call_wall > levels.spot
    assert levels.put_wall == exp["put_wall"] and levels.put_wall < levels.spot

    # zero gamma exists near spot; vol trigger snaps to a listed strike
    assert levels.zero_gamma is not None
    assert abs(levels.zero_gamma - levels.spot) / levels.spot < 0.05
    assert levels.volatility_trigger in {s.strike for s in levels.by_strike}


@pytest.mark.parametrize("symbol", list(EXPECTED))
def test_zero_dte_concentration_present(symbol):
    levels = compute_levels(SampleSource().get_chain(symbol))
    # fixtures include a 0DTE expiry, so some share of gamma must sit there
    assert 0.0 < levels.zero_dte_share < 1.0


def test_top_nodes_ordered():
    levels = compute_levels(SampleSource().get_chain("SPX"))
    pos = [n.net_gex for n in levels.top_positive_nodes]
    neg = [n.net_gex for n in levels.top_negative_nodes]
    assert pos == sorted(pos, reverse=True) and all(v > 0 for v in pos)
    assert neg == sorted(neg) and all(v < 0 for v in neg)


def test_thinkscript_export_contains_levels():
    levels = compute_levels(SampleSource().get_chain("SPX"))
    script = render_thinkscript(levels)
    assert f"input callWall = {levels.call_wall:.2f};" in script
    assert f"input putWall = {levels.put_wall:.2f};" in script
    assert "AddLabel" in script and "Zero Gamma" in script
