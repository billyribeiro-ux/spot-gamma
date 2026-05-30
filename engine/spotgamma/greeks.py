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


def bs_gamma(
    spot: float,
    strike: float,
    t_years: float,
    iv: float,
    rate: float = 0.04,
) -> float:
    """Per-share Black-Scholes gamma.

    Returns 0.0 for degenerate inputs (expired, zero vol, zero spot) rather
    than raising — at expiry gamma is effectively a spike we don't model, and
    callers aggregate many contracts where a hard error would be unhelpful.
    """
    if spot <= 0 or strike <= 0 or t_years <= 0 or iv <= 0:
        return 0.0
    sigma_sqrt_t = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * t_years) / sigma_sqrt_t
    return _norm_pdf(d1) / (spot * sigma_sqrt_t)
