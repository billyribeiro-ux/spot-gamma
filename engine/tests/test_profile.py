"""Net-GEX profile and Zero Gamma crossing detection."""

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
        ProfilePoint(90, 10.0),
        ProfilePoint(91, -10.0),  # crossing ~90.5
        ProfilePoint(99, -10.0),
        ProfilePoint(100, 10.0),  # crossing ~99.5
    ]
    assert find_zero_gamma(profile, spot=100) > 95


def test_sample_chain_has_zero_gamma_near_spot():
    snap = SampleSource().get_chain("SPX")
    profile = gamma_profile(snap)
    zg = find_zero_gamma(profile, snap.spot)
    assert zg is not None
    # designed so the flip sits within a few percent of spot
    assert abs(zg - snap.spot) / snap.spot < 0.05


def test_find_zero_gamma_no_double_count_on_exact_zero_node():
    # An exact-zero node that the curve passes through must be reported once,
    # not duplicated with its neighbouring interpolation.
    profile = [ProfilePoint(98, -200.0), ProfilePoint(100, 0.0), ProfilePoint(102, 200.0)]
    # crossing is exactly the node 100; only candidate -> 100
    assert find_zero_gamma(profile, spot=101) == 100.0


def test_find_zero_gamma_guards_flat_segment():
    # Two equal values (flat) must not divide-by-zero; no crossing here.
    profile = [ProfilePoint(99, 5.0), ProfilePoint(100, 5.0), ProfilePoint(101, -5.0)]
    zg = find_zero_gamma(profile, spot=100)
    assert zg is not None and 100.0 < zg <= 101.0


def test_scalar_and_vectorized_profiles_agree():
    # The two code paths (below/above the vectorize threshold) must produce the
    # same curve on the same chain.
    import spotgamma.profile as P

    snap = SampleSource().get_chain("SPX")
    orig = P._VECTORIZE_THRESHOLD
    try:
        P._VECTORIZE_THRESHOLD = 10**9  # force scalar
        scalar = P.gamma_profile(snap)
        P._VECTORIZE_THRESHOLD = 0  # force vectorized
        vector = P.gamma_profile(snap)
    finally:
        P._VECTORIZE_THRESHOLD = orig
    assert len(scalar) == len(vector)
    for a, b in zip(scalar, vector, strict=True):
        assert abs(a.spot - b.spot) < 1e-9
        # both paths drop zero-OI contracts and use the same BS gamma
        assert abs(a.net_gex - b.net_gex) < 1e-6 * (abs(a.net_gex) + 1.0)
