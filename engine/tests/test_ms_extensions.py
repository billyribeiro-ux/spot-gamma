"""Phase-5 §6/§7 extensions: calendar, gaps, breadth, put/call.

Pure logic, no network. Thresholds trace to docs/MARKET_STRUCTURE.md §6-7.
"""

from datetime import date

from spotgamma.marketstructure.breadth import BreadthRead, breadth_signal, compute_breadth
from spotgamma.marketstructure.calendar import (
    SEASONAL_CAP,
    event_risk,
    is_nfp_heuristic,
    is_third_friday,
    is_triple_witching,
    observed_holiday,
    seasonality,
)
from spotgamma.marketstructure.gaps import Bar, compute_gap_stats
from spotgamma.marketstructure.putcall import PutCallStats, put_call_proxy, put_call_signal, zscore


# --- calendar / event risk (§6.3) -----------------------------------------
def test_opex_and_triple_witching():
    assert is_third_friday(date(2026, 5, 15))  # 3rd Friday of May 2026
    assert not is_third_friday(date(2026, 5, 8))
    assert is_triple_witching(date(2026, 3, 20))  # 3rd Fri of March -> quarterly
    assert not is_triple_witching(date(2026, 5, 15))  # 3rd Fri but not Mar/Jun/Sep/Dec


def test_nfp_heuristic_is_first_friday():
    assert is_nfp_heuristic(date(2026, 5, 1))  # first Friday of May
    assert not is_nfp_heuristic(date(2026, 5, 8))


def test_holiday_detection():
    assert observed_holiday(date(2026, 12, 25)) == "Christmas"
    assert observed_holiday(date(2026, 1, 1)) == "New Year's Day"
    assert observed_holiday(date(2026, 5, 13)) is None


def test_event_risk_never_formula_fakes_fomc():
    # FOMC/CPI must come from the schedule arg, never be inferred.
    quiet = event_risk(date(2026, 5, 13))  # ordinary Wednesday
    assert quiet.events == [] and quiet.score == 0.0 and quiet.label == "quiet"
    # supply FOMC via schedule -> high
    with_fomc = event_risk(date(2026, 5, 13), {date(2026, 5, 13): ["FOMC"]})
    assert "FOMC" in with_fomc.events and with_fomc.score >= 0.8 and with_fomc.label == "high"


def test_event_risk_combines_with_diminishing_returns():
    # triple-witching + FOMC same day: high but not strictly additive past 1.0
    er = event_risk(date(2026, 3, 20), {date(2026, 3, 20): ["FOMC"]})
    assert "triple-witching" in er.events and "FOMC" in er.events
    assert er.score <= 1.0 and er.label == "high"


def test_holiday_returns_quiet_score():
    er = event_risk(date(2026, 12, 25))
    assert er.score == 0.0 and "holiday" in er.events[0]


# --- seasonality (§6.2) — shrunk hard --------------------------------------
def test_seasonality_only_credible_effects_and_capped():
    s = seasonality(date(2026, 5, 1))  # first business day -> turn-of-month
    assert "turn-of-month" in s.factors and 0 < s.tilt <= SEASONAL_CAP
    # an ordinary mid-month day has no tilt
    mid = seasonality(date(2026, 5, 13))
    assert mid.tilt == 0.0 and mid.label == "neutral"


def test_seasonality_excludes_folklore():
    # day-of-week / September must NOT create a tilt on an ordinary day
    sep = seasonality(date(2026, 9, 16))  # mid-September, a Wednesday
    assert sep.tilt == 0.0


# --- gap statistics (§6.1) — size-conditioned ------------------------------
def test_gap_fill_is_size_conditioned_not_blended():
    # build a history: many tiny gaps that fill, plus large gaps that don't.
    bars = [Bar(100, 100, 100, 100)]
    # 10 tiny +0.1% gaps that immediately fill (low dips back to prev close)
    px = 100.0
    for _ in range(10):
        prev = px
        op = prev * 1.001
        bars.append(Bar(op, op * 1.002, prev * 0.999, op))  # low <= prev -> fills
        px = op
    # 5 large +3% gaps that DON'T fill (low stays above prev close)
    for _ in range(5):
        prev = px
        op = prev * 1.03
        bars.append(Bar(op, op * 1.01, op * 0.999, op))  # low > prev -> no fill
        px = op
    gs = compute_gap_stats(bars)
    small = next(b for b in gs.buckets if b.bucket == "0.05-0.25%")
    large = next(b for b in gs.buckets if b.bucket == ">=2%")
    assert small.count == 10 and small.fill_rate == 1.0
    assert large.count == 5 and large.fill_rate == 0.0  # the headline-70% trap avoided
    # empty buckets report None, not a fake 0
    mid = next(b for b in gs.buckets if b.bucket == "0.5-1%")
    assert mid.count == 0 and mid.fill_rate is None


def test_gap_dead_zone_ignores_noise():
    bars = [Bar(100, 101, 99, 100), Bar(100.01, 100.5, 99.5, 100.2)]  # +0.01% < dead zone
    gs = compute_gap_stats(bars)
    assert gs.n_sessions == 0  # below the 0.05% dead zone, not counted


# --- breadth (§7) ----------------------------------------------------------
def test_breadth_percent_above_ma():
    # A: 60 bars flat (has 50dma, not 200); B: 200 bars then up; C: 200 then down
    closes = {
        "A": [10.0] * 60,
        "B": [10.0] * 199 + [12.0],
        "C": [10.0] * 199 + [8.0],
    }
    b = compute_breadth(closes)
    assert b.n_constituents == 3
    # 200dma: B above (12>10), C below (8<10) -> 50%
    assert b.pct_above_200dma == 50.0


def test_breadth_signal_healthy_vs_washed_out():
    healthy = breadth_signal(BreadthRead(pct_above_50dma=80, pct_above_200dma=75, advancers_pct=70, n_constituents=500))
    assert healthy is not None and healthy.score < 0  # broad participation = risk-on
    washed = breadth_signal(BreadthRead(pct_above_50dma=20, pct_above_200dma=22, advancers_pct=25, n_constituents=500))
    assert washed.score > 0.5  # washed out = risk-off
    assert breadth_signal(BreadthRead(None, None, None, 0)) is None  # no data -> abstain


# --- put/call (§7) — z-scored, contrarian ----------------------------------
def test_put_call_proxy_and_zscore():
    assert put_call_proxy(1200, 1000) == 1.2
    assert put_call_proxy(500, 0) is None  # no calls
    z, pct = zscore(1.2, [0.8, 0.9, 1.0, 0.7, 0.85] * 5)
    assert z is not None and z > 0  # 1.2 is above the ~0.85 mean
    assert pct is not None and pct > 50
    # too little history -> no z
    assert zscore(1.0, [0.9, 1.0])[0] is None


def test_put_call_signal_is_contrarian():
    # extreme fear (high z) -> contrarian risk-ON (negative score)
    fear = put_call_signal(PutCallStats(ratio=1.4, z=2.0, percentile=98))
    assert fear.label == "fearful" and fear.score < 0
    # complacency (low z) -> risk-OFF (positive)
    greed = put_call_signal(PutCallStats(ratio=0.5, z=-2.0, percentile=3))
    assert greed.label == "complacent" and greed.score > 0
    # no history -> abstain
    na = put_call_signal(PutCallStats(ratio=0.9, z=None, percentile=None))
    assert na.score == 0.0
