"""Black-Scholes gamma.

Two uses:

1. **Fallback** — fill ``OptionContract.gamma`` when a data source provides IV
   but not greeks.
2. **Profile mode** — recompute gamma at hypothetical spot levels so the
   net-GEX curve (and therefore the Zero Gamma crossing) reflects how dealer
   hedging changes as price moves, not just the static snapshot.

Gamma is identical for a call and a put at the same strike/expiry/vol, so a
single function serves both.
"""

from __future__ import annotations

import math

_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def bs_gamma_array(spot, strike, t_years, iv, rate=0.04, div_yield=0.0):
    """Vectorized per-share gamma for one spot against arrays of contracts.

    Carry-adjusted Black-Scholes (Merton): the drift in ``d1`` is ``r - q`` and
    gamma carries the ``e^{-qT}`` factor, where ``q`` is the continuous dividend
    yield. ``q=0`` reduces to plain Black-Scholes. Mirrors :func:`bs_gamma` but
    operates on numpy arrays so the profile can evaluate tens of thousands of
    contracts per grid step. Degenerate contracts (expired / zero vol) yield 0.0.
    """
    import numpy as np

    strike = np.asarray(strike, dtype=float)
    t_years = np.asarray(t_years, dtype=float)
    iv = np.asarray(iv, dtype=float)
    valid = (spot > 0) & (strike > 0) & (t_years > 0) & (iv > 0)
    safe_t = np.where(valid, t_years, 1.0)
    safe_iv = np.where(valid, iv, 1.0)
    sigma_sqrt_t = safe_iv * np.sqrt(safe_t)
    d1 = (np.log(spot / np.where(valid, strike, 1.0)) + (rate - div_yield + 0.5 * safe_iv**2) * safe_t) / sigma_sqrt_t
    pdf = np.exp(-0.5 * d1 * d1) / _SQRT_2PI
    return np.where(valid, np.exp(-div_yield * safe_t) * pdf / (spot * sigma_sqrt_t), 0.0)


def bs_gamma(
    spot: float,
    strike: float,
    t_years: float,
    iv: float,
    rate: float = 0.04,
    div_yield: float = 0.0,
) -> float:
    """Per-share carry-adjusted Black-Scholes (Merton) gamma.

    ``d1`` drift is ``r - q`` and gamma carries the ``e^{-qT}`` factor, where
    ``q`` is the continuous dividend yield (``q=0`` -> plain Black-Scholes).
    Returns 0.0 for degenerate inputs (expired, zero vol, zero spot) rather than
    raising — callers aggregate many contracts where a hard error is unhelpful.
    """
    if spot <= 0 or strike <= 0 or t_years <= 0 or iv <= 0:
        return 0.0
    sigma_sqrt_t = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * iv * iv) * t_years) / sigma_sqrt_t
    return math.exp(-div_yield * t_years) * _norm_pdf(d1) / (spot * sigma_sqrt_t)
