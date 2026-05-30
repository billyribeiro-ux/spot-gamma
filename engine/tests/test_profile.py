"""Net-GEX profile and Zero Gamma crossing detection."""
from datetime import datetime

from spotgamma.profile import ProfilePoint, find_zero_gamma, gamma_profile
from spotgamma.sources.sample import SampleSource


def test_find_zero_gamma_interpolates_crossing():
    # Net GEX goes negative below 100, positive above -> crossing at 100.
    profile = [ProfilePoint(98, -200.0), ProfilePoint(100, 0.0), ProfilePoint(102, 200.0)]
    assert find_zero_gamma(profile, spot=100) == 100.0


def test_find_zero_gamma_linear_interpolation_off_grid():
    # Crossing halfway between 99 and 101 -> 100.
    profile = [ProfilePoint(99, -100.0), ProfilePoint(101, 100.0)]
    assert abs(find_zero_gamma(profile, spot=100) - 100.0) < 1e-9


def test_find_zero_gamma_none_when_no_sign_change():
    profile = [ProfilePoint(99, 50.0), ProfilePoint(100, 80.0), ProfilePoint(101, 120.0)]
    assert find_zero_gamma(profile, spot=100) is None


def test_find_zero_gamma_picks_nearest_to_spot():
    # Two crossings; nearest to spot=100 should win.
    profile = [
        ProfilePoint(90, 10.0), ProfilePoint(91, -10.0),  # crossing ~90.5
        ProfilePoint(99, -10.0), ProfilePoint(100, 10.0),  # crossing ~99.5
    ]
    assert find_zero_gamma(profile, spot=100) > 95


def test_sample_chain_has_zero_gamma_near_spot():
    snap = SampleSource().get_chain("SPX")
    profile = gamma_profile(snap)
    zg = find_zero_gamma(profile, snap.spot)
    assert zg is not None
    # designed so the flip sits within a few percent of spot
    assert abs(zg - snap.spot) / snap.spot < 0.05
