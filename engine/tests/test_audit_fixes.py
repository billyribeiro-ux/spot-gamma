"""Regression tests for the adversarially-verified audit fixes.

Each test pins one confirmed correctness/accuracy bug so it cannot silently
return. Titles reference the finding they lock down.
"""

from datetime import UTC, date, datetime

import pytest
from spotgamma.greeks import bs_gamma
from spotgamma.history import parse_yahoo_chart
from spotgamma.levels import compute_levels
from spotgamma.marketstructure.calendar import _is_turn_of_month, observed_holiday
from spotgamma.marketstructure.composite import compose
from spotgamma.marketstructure.signals import (
    credit_signal,
    gamma_modifier,
    vix_signal,
    vol_regime,
    yield_curve_signal,
)
from spotgamma.models import MIN_DTE_YEARS, ChainSnapshot, OptionContract, OptionType
from spotgamma.profile import ProfilePoint, find_zero_gamma, gamma_profile
from spotgamma.sources._normalize import normalize_iv


def _zerodte_iv_chain() -> ChainSnapshot:
    """A full same-day-expiry chain with IV only (no source gamma) — the path that
    previously zeroed every 0DTE contract."""
    exp = date(2026, 6, 25)
    ts = datetime(2026, 6, 25, 14, 0, tzinfo=UTC)  # ~10:00 ET, same session
    oi = {(5100, "c"): 20000, (4900, "p"): 20000}  # asymmetric: call/put walls
    contracts = []
    for k in (4900, 4950, 5000, 5050, 5100):
        for ot in (OptionType.CALL, OptionType.PUT):
            tag = "c" if ot is OptionType.CALL else "p"
            contracts.append(
                OptionContract(
                    option_type=ot,
                    strike=k,
                    expiration=exp,
                    open_interest=oi.get((k, tag), 3000),
                    implied_volatility=0.15,
                    gamma=None,
                )
            )
    return ChainSnapshot(symbol="SPX", spot=5000.0, timestamp=ts, contracts=contracts)


# --- CRITICAL: 0DTE time-to-expiry floor -----------------------------------
def test_zerodte_gamma_is_floored_finite_not_zero():
    snap = _zerodte_iv_chain()
    # the floor makes same-day T strictly positive (was 0.0 -> gamma deleted)
    assert snap.dte(date(2026, 6, 25)) == pytest.approx(MIN_DTE_YEARS)
    assert bs_gamma(5000, 5000, snap.dte(date(2026, 6, 25)), 0.15) > 0  # finite, was 0.0


def test_zerodte_chain_produces_levels_via_iv_fallback():
    lv = compute_levels(_zerodte_iv_chain())
    # walls + net GEX + 0DTE share all populated (previously all None/0)
    assert lv.net_gex != 0.0
    assert lv.call_wall == 5100.0 and lv.put_wall == 4900.0
    assert lv.zero_dte_share == pytest.approx(1.0)


def test_profile_carries_zerodte_gamma_off_snapshot():
    from spotgamma.profile import make_net_gex_fn

    net_at = make_net_gex_fn(_zerodte_iv_chain())
    # the net-GEX curve (which drives Zero Gamma) now sees 0DTE gamma at any spot
    assert net_at(4970.0) != 0.0 and net_at(5030.0) != 0.0


def test_dte_is_intraday_aware():
    # a morning snapshot carries more time-to-expiry than an afternoon one
    morning = ChainSnapshot(
        symbol="SPX", spot=5000.0, timestamp=datetime(2026, 6, 24, 13, 30, tzinfo=UTC), contracts=[]
    )
    afternoon = ChainSnapshot(
        symbol="SPX", spot=5000.0, timestamp=datetime(2026, 6, 24, 19, 30, tzinfo=UTC), contracts=[]
    )
    exp = date(2026, 6, 26)
    assert morning.dte(exp) > afternoon.dte(exp)


# --- HIGH: flat-profile spurious crossing ----------------------------------
def test_flat_zero_profile_has_no_zero_gamma():
    flat = [ProfilePoint(99.0, 0.0), ProfilePoint(100.0, 0.0), ProfilePoint(101.0, 0.0)]
    assert find_zero_gamma(flat, spot=100.0) is None


def test_genuine_zero_node_still_detected():
    # a real sign change through an exact-zero node is still a crossing
    p = [ProfilePoint(98.0, -200.0), ProfilePoint(100.0, 0.0), ProfilePoint(102.0, 200.0)]
    assert find_zero_gamma(p, spot=100.0) == 100.0


def test_empty_chain_profile_zero_gamma_is_none():
    snap = ChainSnapshot(symbol="SPX", spot=5000.0, timestamp=datetime(2026, 6, 25, 14, 0, tzinfo=UTC), contracts=[])
    prof = gamma_profile(snap)
    assert find_zero_gamma(prof, snap.spot) is None  # all-zero curve -> no flip


# --- LOW: gamma_profile steps guard ----------------------------------------
def test_gamma_profile_rejects_degenerate_steps():
    snap = ChainSnapshot(symbol="SPX", spot=5000.0, timestamp=datetime(2026, 6, 25, 14, 0, tzinfo=UTC), contracts=[])
    with pytest.raises(ValueError):
        gamma_profile(snap, steps=1)


# --- MEDIUM: New Year's observed across the month boundary ------------------
def test_new_years_observed_on_friday_dec31():
    # Dec 31 2027 is a Friday; New Year's (Jan 1, Sat) is observed that Friday
    assert observed_holiday(date(2027, 12, 31)) == "New Year's Day (observed)"


def test_existing_holiday_detection_unchanged():
    assert observed_holiday(date(2026, 12, 25)) == "Christmas"
    assert observed_holiday(date(2026, 1, 1)) == "New Year's Day"


# --- LOW: turn-of-month must not flag weekend dates -------------------------
def test_turn_of_month_excludes_weekends():
    # 2026-08-01 is a Saturday — not a trading day, must not be turn-of-month
    assert date(2026, 8, 1).weekday() == 5
    assert _is_turn_of_month(date(2026, 8, 1)) is False


# --- MEDIUM: context-only yield curve must not drive divergence -------------
def test_yield_curve_excluded_from_divergence():
    # vix risk-on + an inverted (risk-off) curve: the curve is context-only, so
    # this must NOT register as a divergence (only summed signals can diverge).
    read = compose(
        [vix_signal(12), yield_curve_signal(-0.6)],
        vol_regime_label="calm",
        net_gex=1e10,
        spot=7500,
        zero_gamma=7400,
    )
    assert read.divergence is False
    # a real disagreement among summed signals still triggers it
    real = compose([vix_signal(11), credit_signal(7.5)], vol_regime_label="normal")
    assert real.divergence is True


# --- LOW: NaN/degenerate guards on the gamma gate + vol regime --------------
def test_gamma_modifier_neutral_on_nan():
    nan = float("nan")
    assert gamma_modifier(nan, 5000, 4900) == 1.0
    assert gamma_modifier(1e10, nan, 4900) == 1.0
    assert gamma_modifier(1e10, 5000, nan) in (0.5, 1.0) or 0.5 <= gamma_modifier(1e10, 5000, nan) <= 1.5
    # a NaN zero_gamma must not poison the distance term
    assert 0.5 <= gamma_modifier(1e10, 5000, nan) <= 1.5


def test_vol_regime_defined_on_nan():
    assert vol_regime(float("nan"), 0.9, 85.0) == "normal"


# --- MEDIUM: Yahoo parse tolerates ragged arrays ---------------------------
def test_yahoo_parse_handles_ragged_arrays():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "X"},
                    "timestamp": [1000, 2000, 3000],  # 3 timestamps
                    "indicators": {
                        "quote": [
                            {  # but only 2 OHLC entries (truncated payload)
                                "open": [10.0, 11.0],
                                "high": [10.5, 11.5],
                                "low": [9.5, 10.5],
                                "close": [10.2, 11.2],
                                "volume": [100],  # even shorter volume
                            }
                        ]
                    },
                }
            ]
        }
    }
    bars, _meta = parse_yahoo_chart(payload)
    assert len(bars) == 2  # bounded to the shortest OHLC array, no IndexError
    assert bars[1].volume == 0.0  # missing volume defaults to 0


# --- MEDIUM: IV unit is explicit per source --------------------------------
def test_normalize_iv_explicit_units():
    assert normalize_iv(16.0, "percent") == 0.16
    assert normalize_iv(0.16, "decimal") == 0.16
    # explicit decimal does NOT divide a genuine high IV (350%) — the heuristic bug
    assert normalize_iv(3.5, "decimal") == 3.5
    # explicit percent does divide a sub-3 percent-point IV the heuristic missed
    assert normalize_iv(2.5, "percent") == 0.025
    # auto keeps the documented heuristic + sentinel handling
    assert normalize_iv(16.0) == 0.16
    assert normalize_iv(-999.0, "percent") is None


# --- MEDIUM: put/call z-score baseline must exclude today (no self-reference) -
def test_put_call_baseline_excludes_today(tmp_path):
    from spotgamma.marketstructure.feeds import put_call_baseline, update_put_call_history

    p = tmp_path / "putcall_history.json"
    for i in range(1, 21):  # 20 prior days at ~1.0
        update_put_call_history(1.0, today=date(2026, 1, i), path=str(p))
    # today's extreme reading must be scored against the PRIOR window, not itself
    today = date(2026, 1, 21)
    update_put_call_history(2.0, today=today, path=str(p))
    baseline = put_call_baseline(today=today, path=str(p))
    assert 2.0 not in baseline  # today excluded
    assert len(baseline) == 20 and all(x == 1.0 for x in baseline)
