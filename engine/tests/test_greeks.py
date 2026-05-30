"""Black-Scholes gamma: scalar/vector agreement, degeneracy, dividend carry."""

import math

from spotgamma.greeks import bs_gamma, bs_gamma_array


def test_scalar_matches_array():
    args = (100.0, 105.0, 0.25, 0.20)
    scalar = bs_gamma(*args)
    arr = float(bs_gamma_array(100.0, [105.0], [0.25], [0.20])[0])
    assert abs(scalar - arr) < 1e-12


def test_degenerate_inputs_return_zero():
    assert bs_gamma(100, 100, 0.0, 0.2) == 0.0  # expired
    assert bs_gamma(100, 100, 0.25, 0.0) == 0.0  # zero vol
    assert bs_gamma(0, 100, 0.25, 0.2) == 0.0  # zero spot


def test_atm_gamma_is_positive_and_peaks_near_the_money():
    t, iv = 0.25, 0.20
    atm = bs_gamma(100, 100, t, iv)
    otm = bs_gamma(100, 130, t, iv)
    assert atm > 0 and atm > otm


def test_dividend_yield_adjusts_gamma_via_merton_carry():
    # Merton gamma carries e^{-qT} and shifts d1's drift to (r - q). The net
    # effect on ATM gamma is small and not necessarily monotone, so we assert
    # the model identity rather than a direction.
    s, k, t, iv, r, q = 100.0, 100.0, 1.0, 0.20, 0.04, 0.03
    plain = bs_gamma(s, k, t, iv, r, 0.0)
    with_div = bs_gamma(s, k, t, iv, r, q)
    assert with_div != plain  # q actually changes the result
    assert 0.9 < with_div / plain < 1.1  # but only modestly near the money

    # closed-form check: gamma = e^{-qT} * phi(d1) / (S*sigma*sqrt(T))
    sst = iv * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * iv * iv) * t) / sst
    expected = math.exp(-q * t) * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (s * sst)
    assert abs(with_div - expected) < 1e-12

    # scalar and array paths agree with the dividend term applied
    arr = float(bs_gamma_array(s, [k], [t], [iv], r, q)[0])
    assert abs(arr - with_div) < 1e-12
