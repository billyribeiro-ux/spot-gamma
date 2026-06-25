"""Net-GEX profile across a spot grid -> Zero Gamma level.

A snapshot net-GEX number tells you today's regime, but the *Zero Gamma* level
is where net dealer gamma would flip sign as spot moves. To find it honestly we
recompute every contract's gamma (carry-adjusted Black-Scholes) at hypothetical
spot levels and locate where the aggregate net-GEX curve crosses zero, then
refine that crossing below grid resolution with bisection.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from .greeks import bs_gamma_array
from .models import ChainSnapshot, OptionType

_FALLBACK_IV = 0.20


class ProfilePoint(NamedTuple):
    spot: float
    net_gex: float


def make_net_gex_fn(snap: ChainSnapshot) -> Callable[[float], float]:
    """Build a fast ``net_gex(spot)`` evaluator over the OI-bearing chain.

    Contracts are prepared into numpy arrays once; the returned closure then
    evaluates aggregate net GEX at any hypothetical spot in a single vectorized
    pass. Reused for both the profile grid and bisection refinement, guaranteeing
    they share one consistent Black-Scholes basis. Zero-OI contracts contribute
    nothing and are dropped up front.
    """
    import numpy as np

    contracts = [c for c in snap.contracts if c.open_interest > 0]
    if not contracts:
        return lambda _s: 0.0

    strike = np.array([c.strike for c in contracts], dtype=float)
    t_years = np.array([snap.dte(c.expiration) for c in contracts], dtype=float)
    iv = np.array([c.implied_volatility or _FALLBACK_IV for c in contracts], dtype=float)
    # signed OI folds the dealer call(+)/put(-) convention into one weight
    signed_oi = np.array(
        [c.open_interest if c.option_type is OptionType.CALL else -c.open_interest for c in contracts],
        dtype=float,
    )
    mult, rate, q = snap.multiplier, snap.risk_free_rate, snap.dividend_yield

    def net_at(spot: float) -> float:
        gamma = bs_gamma_array(spot, strike, t_years, iv, rate, q)
        return float((gamma * signed_oi).sum() * mult * spot * spot * 0.01)

    return net_at


def gamma_profile(
    snap: ChainSnapshot,
    width: float = 0.15,
    steps: int = 121,
    net_fn: Callable[[float], float] | None = None,
) -> list[ProfilePoint]:
    """Net GEX evaluated across spot in ``[spot*(1-width), spot*(1+width)]``."""
    if steps < 2:
        raise ValueError("steps must be >= 2 to span a grid")
    net_at = net_fn or make_net_gex_fn(snap)
    lo, hi = snap.spot * (1 - width), snap.spot * (1 + width)
    spots = (lo + i * (hi - lo) / (steps - 1) for i in range(steps))
    return [ProfilePoint(s, net_at(s)) for s in spots]


def _bisect(net_fn: Callable[[float], float], lo: float, hi: float, iters: int = 50) -> float:
    """Refine a bracketed zero of ``net_fn`` on ``[lo, hi]`` via bisection."""
    flo = net_fn(lo)
    fhi = net_fn(hi)
    if flo == 0.0:
        return lo
    if fhi == 0.0 or (flo > 0) == (fhi > 0):
        return hi if fhi == 0.0 else (lo + hi) / 2  # not bracketed -> midpoint
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = net_fn(mid)
        if fm == 0.0:
            return mid
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def find_zero_gamma(
    profile: list[ProfilePoint],
    spot: float,
    net_fn: Callable[[float], float] | None = None,
) -> float | None:
    """Spot level where the net-GEX curve crosses zero, nearest to current spot.

    Detects crossings by a strict sign change between adjacent points, and treats
    an exact-zero node as a crossing **only when the curve genuinely changes sign
    across it** (its nearest non-zero neighbours on each side have opposite signs).
    That neighbour check is what stops a flat, identically-zero profile — e.g. a
    chain with no OI, where ``net_at`` returns 0 everywhere — from reporting every
    node as a spurious flip. When ``net_fn`` is supplied the chosen crossing is
    refined with bisection on the real curve, so precision isn't capped by the grid
    step (~0.25% otherwise). Returns ``None`` when the curve never changes sign.
    """
    n = len(profile)
    if n < 2:
        return None
    spots = [p.spot for p in profile]
    gex = [p.net_gex for p in profile]

    # each crossing: (linear_estimate, bracket_lo, bracket_hi)
    crossings: list[tuple[float, float, float]] = []
    for i in range(n - 1):
        g0, g1 = gex[i], gex[i + 1]
        s0, s1 = spots[i], spots[i + 1]
        if g0 == 0.0:
            # Real crossing iff the nearest non-zero values on each side straddle
            # zero. A flat all-zero curve has no such neighbours -> no crossing.
            left = next((g for g in reversed(gex[:i]) if g != 0.0), None)
            right = next((g for g in gex[i + 1 :] if g != 0.0), None)
            if left is not None and right is not None and (left > 0) != (right > 0):
                crossings.append((s0, s0, s0))
        elif g0 * g1 < 0:  # opposite signs -> denominator (g1 - g0) is nonzero
            est = s0 + (s1 - s0) * (-g0) / (g1 - g0)
            crossings.append((est, s0, s1))
    if not crossings:
        return None

    est, lo, hi = min(crossings, key=lambda c: abs(c[0] - spot))
    if net_fn is None or lo == hi:
        return est
    return _bisect(net_fn, lo, hi)
