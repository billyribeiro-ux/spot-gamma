"""End-to-end level computation on the sample fixtures."""

from datetime import UTC

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


@pytest.mark.parametrize("symbol", list(EXPECTED))
def test_absolute_gamma_and_hedge_wall(symbol):
    levels = compute_levels(SampleSource().get_chain(symbol))
    by_strike = {s.strike: s for s in levels.by_strike}

    # both resolve to listed strikes
    assert levels.absolute_gamma in by_strike
    assert levels.hedge_wall in by_strike

    # absolute gamma = the strike with the most TOTAL gamma (calls + puts)
    assert levels.absolute_gamma == max(levels.by_strike, key=lambda s: s.total_abs_gex).strike
    # hedge wall = the strike with the largest NET gamma magnitude
    assert levels.hedge_wall == max(levels.by_strike, key=lambda s: abs(s.net_gex)).strike


def test_top_nodes_ordered():
    levels = compute_levels(SampleSource().get_chain("SPX"))
    pos = [n.net_gex for n in levels.top_positive_nodes]
    neg = [n.net_gex for n in levels.top_negative_nodes]
    assert pos == sorted(pos, reverse=True) and all(v > 0 for v in pos)
    assert neg == sorted(neg) and all(v < 0 for v in neg)


def test_thinkscript_export_contains_levels():
    levels = compute_levels(SampleSource().get_chain("SPX"))
    script = render_thinkscript(levels)
    # all six levels are emitted as numeric inputs
    assert f"input callWall = {levels.call_wall:.2f};" in script
    assert f"input putWall = {levels.put_wall:.2f};" in script
    assert "input absGamma" in script and "input hedgeWall" in script
    # Phase 4 features: labels, flip-zone cloud, regime background, alerts
    assert "AddLabel" in script and "Gamma Flip" in script
    assert "AddCloud" in script  # flip zone
    assert "AssignBackgroundColor" in script  # color-coded regime state
    assert "Alert(" in script and "Crosses(" in script  # alert conditions
    # colors aligned with the dashboard: call wall green, put wall red
    assert "CallWallLine.SetDefaultColor(CreateColor(46, 211, 144))" in script
    assert "PutWallLine.SetDefaultColor(CreateColor(255, 82, 105))" in script


def _snap(contracts, spot=100.0):
    from datetime import datetime

    from spotgamma.models import ChainSnapshot

    return ChainSnapshot(
        symbol="TEST",
        spot=spot,
        timestamp=datetime(2026, 1, 5, 18, 0, tzinfo=UTC),
        contracts=contracts,
    )


def test_empty_chain_returns_no_data_not_crash():
    # Regression: _absolute_gamma/_hedge_wall did max([]) -> ValueError on empty.
    levels = compute_levels(_snap([]))
    assert levels.net_gex == 0.0 and levels.by_strike == []
    assert levels.call_wall is None and levels.put_wall is None
    assert levels.absolute_gamma is None and levels.hedge_wall is None
    assert levels.zero_dte_share == 0.0


def test_negative_gamma_regime():
    from datetime import date

    from spotgamma.models import OptionContract, OptionType

    exp = date(2026, 2, 20)
    contracts = [
        OptionContract(option_type=OptionType.PUT, strike=95, expiration=exp, open_interest=8000, gamma=0.05),
        OptionContract(option_type=OptionType.CALL, strike=105, expiration=exp, open_interest=200, gamma=0.01),
    ]
    levels = compute_levels(_snap(contracts))
    assert levels.net_gex < 0 and levels.regime == "negative"
    assert levels.put_wall == 95  # the dominant short-gamma shelf
