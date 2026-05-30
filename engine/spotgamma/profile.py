"""Net-GEX profile across a spot grid -> Zero Gamma level.

A snapshot net-GEX number tells you today's regime, but the *Zero Gamma* level
is where net dealer gamma would flip sign as spot moves. To find it honestly we
recompute every contract's gamma (Black-Scholes) at a grid of hypothetical spot
levels and locate where the aggregate net-GEX curve crosses zero.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

from .greeks import bs_gamma_array
from .models import ChainSnapshot, OptionType

# Below this contract count the pure-Python path is plenty fast and avoids the
# numpy import; above it we vectorize (real index chains are tens of thousands).
_VECTORIZE_THRESHOLD = 2000

_FALLBACK_IV = 0.20


class ProfilePoint(NamedTuple):
    spot: float
    net_gex: float


def gamma_profile(
    snap: ChainSnapshot,
    width: float = 0.15,
    steps: int = 121,
) -> list[ProfilePoint]:
    """Net GEX evaluated across spot in ``[spot*(1-width), spot*(1+width)]``.

    Contracts with zero open interest contribute exactly zero GEX, so they are
    dropped up front — both a correctness-preserving speedup and what lets a
    30k-contract chain profile in well under a second.
    """
    contracts = [c for c in snap.contracts if c.open_interest > 0]
    lo, hi = snap.spot * (1 - width), snap.spot * (1 + width)
    spots = [lo + i * (hi - lo) / (steps - 1) for i in range(steps)]

    if len(contracts) < _VECTORIZE_THRESHOLD:
        from .gex import net_gex  # scalar path reuses the per-contract function

        return [ProfilePoint(s, net_gex(snap, s)) for s in spots]

    import numpy as np

    mult = snap.multiplier
    strike = np.array([c.strike for c in contracts])
    t_years = np.array([snap.dte(c.expiration) for c in contracts])
    iv = np.array([c.implied_volatility or _FALLBACK_IV for c in contracts])
    # signed open interest folds the dealer call(+)/put(-) convention into one weight
    signed_oi = np.array([c.open_interest if c.option_type is OptionType.CALL else -c.open_interest for c in contracts])

    points: list[ProfilePoint] = []
    for s in spots:
        gamma = bs_gamma_array(s, strike, t_years, iv, snap.risk_free_rate)
        net = float(np.sum(gamma * signed_oi) * mult * s * s * 0.01)
        points.append(ProfilePoint(s, net))
    return points


def find_zero_gamma(profile: list[ProfilePoint], spot: float) -> Optional[float]:
    """Spot level where the net-GEX curve crosses zero.

    Returns the crossing nearest to current spot via linear interpolation. If
    the curve never changes sign across the grid there is no flip in range and
    we return ``None`` (e.g. deeply positive- or negative-gamma all the way).
    """
    crossings: list[float] = []
    for (s0, g0), (s1, g1) in zip(profile, profile[1:]):
        if g0 == 0.0:
            crossings.append(s0)
        if (g0 < 0) != (g1 < 0) and g0 != 0.0:
            # linear interpolation for the zero between the two grid points
            crossings.append(s0 + (s1 - s0) * (-g0) / (g1 - g0))
    if not crossings:
        return None
    return min(crossings, key=lambda x: abs(x - spot))
