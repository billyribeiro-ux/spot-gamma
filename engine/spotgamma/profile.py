"""Net-GEX profile across a spot grid -> Zero Gamma level.

A snapshot net-GEX number tells you today's regime, but the *Zero Gamma* level
is where net dealer gamma would flip sign as spot moves. To find it honestly we
recompute every contract's gamma (Black-Scholes) at a grid of hypothetical spot
levels and locate where the aggregate net-GEX curve crosses zero.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

from .gex import net_gex
from .models import ChainSnapshot


class ProfilePoint(NamedTuple):
    spot: float
    net_gex: float


def gamma_profile(
    snap: ChainSnapshot,
    width: float = 0.15,
    steps: int = 121,
) -> list[ProfilePoint]:
    """Net GEX evaluated across spot in ``[spot*(1-width), spot*(1+width)]``."""
    lo, hi = snap.spot * (1 - width), snap.spot * (1 + width)
    step = (hi - lo) / (steps - 1)
    return [ProfilePoint(s := lo + i * step, net_gex(snap, s)) for i in range(steps)]


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
