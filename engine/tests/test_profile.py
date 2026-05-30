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


def test_profile_matches_standalone_evaluator():
    # The profile grid and the standalone net_gex evaluator share one basis.
    from spotgamma.profile import make_net_gex_fn

    snap = SampleSource().get_chain("SPX")
    net_at = make_net_gex_fn(snap)
    profile = gamma_profile(snap, net_fn=net_at)
    for p in profile:
        assert abs(p.net_gex - net_at(p.spot)) < 1e-6 * (abs(p.net_gex) + 1.0)


def test_bisection_refines_zero_gamma_onto_the_real_curve():
    # With a net_fn, the returned crossing should sit essentially on net=0,
    # tighter than the linear grid estimate.
    from spotgamma.profile import make_net_gex_fn

    snap = SampleSource().get_chain("SPX")
    net_at = make_net_gex_fn(snap)
    profile = gamma_profile(snap, net_fn=net_at)
    linear = find_zero_gamma(profile, snap.spot)
    refined = find_zero_gamma(profile, snap.spot, net_fn=net_at)
    assert linear is not None and refined is not None
    # the refined crossing evaluates much closer to zero than the linear estimate
    assert abs(net_at(refined)) <= abs(net_at(linear)) + 1e-6
    assert abs(net_at(refined)) < 1e-3 * abs(net_at(snap.spot) or 1.0)
