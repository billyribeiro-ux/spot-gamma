"""Turn a chain snapshot into finished dealer-facing gamma levels.

This is the single orchestration point that the CLI and API call. Every level
here is defined explicitly in docs/METHODOLOGY.md so the numbers are auditable.
"""

from __future__ import annotations

from .gex import aggregate_all
from .models import ChainSnapshot, GammaLevels, StrikeGamma
from .profile import find_zero_gamma, gamma_profile, make_net_gex_fn


def _call_wall(strikes: list[StrikeGamma], spot: float) -> float | None:
    """Largest positive net-gamma strike at/above spot (resistance shelf).

    Keyed on *net* GEX rather than raw call gamma so the near-ATM 0DTE gamma
    spike (where call and put gamma cancel) doesn't masquerade as the wall.
    """
    above = [s for s in strikes if s.strike >= spot and s.net_gex > 0]
    pool = above or [s for s in strikes if s.net_gex > 0]
    return max(pool, key=lambda s: s.net_gex).strike if pool else None


def _put_wall(strikes: list[StrikeGamma], spot: float) -> float | None:
    """Most negative net-gamma strike at/below spot (support shelf)."""
    below = [s for s in strikes if s.strike <= spot and s.net_gex < 0]
    pool = below or [s for s in strikes if s.net_gex < 0]
    return min(pool, key=lambda s: s.net_gex).strike if pool else None


def _volatility_trigger(strikes: list[StrikeGamma], spot: float, zero_gamma: float | None) -> float | None:
    """Actionable strike-snapped gamma flip.

    Traders act on a tradable level, so the Volatility Trigger is the listed
    strike nearest the (continuous) Zero Gamma crossing — the price at which
    dealer hedging flips from dampening to amplifying. Falls back to the
    largest positive net-gamma strike when no flip exists in range.
    """
    if not strikes:
        return None
    if zero_gamma is not None:
        return min(strikes, key=lambda s: abs(s.strike - zero_gamma)).strike
    positive = [s for s in strikes if s.net_gex > 0]
    return max(positive, key=lambda s: s.net_gex).strike if positive else None


def _absolute_gamma(strikes: list[StrikeGamma]) -> float | None:
    """Strike holding the most *total* option gamma (calls + puts, side-agnostic).

    SpotGamma's "Absolute Gamma" — the single largest gamma concentration, which
    tends to act as the strongest magnet/pin. Distinct from the walls (net gamma)
    because near-ATM strikes can stack large call *and* put gamma at once.
    """
    return max(strikes, key=lambda s: s.total_abs_gex).strike if strikes else None


def _hedge_wall(strikes: list[StrikeGamma]) -> float | None:
    """Strike with the largest *net* dealer gamma magnitude (the dominant wall).

    SpotGamma's "Hedge Wall" — the level around which dealer hedging flux is
    greatest; we take the strike whose net GEX is largest in absolute terms,
    whichever side of spot it sits on.
    """
    return max(strikes, key=lambda s: abs(s.net_gex)).strike if strikes else None


def _empty_levels(snap: ChainSnapshot) -> GammaLevels:
    """Well-formed 'no data' result for an empty chain (avoids max([]) crashes)."""
    return GammaLevels(
        symbol=snap.symbol,
        spot=snap.spot,
        timestamp=snap.timestamp,
        net_gex=0.0,
        regime="positive",
        zero_gamma=None,
        volatility_trigger=None,
        call_wall=None,
        put_wall=None,
        absolute_gamma=None,
        hedge_wall=None,
        top_positive_nodes=[],
        top_negative_nodes=[],
        by_strike=[],
        by_expiry=[],
        zero_dte_net_gex=0.0,
        zero_dte_share=0.0,
    )


def compute_levels(
    snap: ChainSnapshot,
    top_n: int = 5,
    profile_width: float = 0.15,
    profile_steps: int = 121,
) -> GammaLevels:
    # One pass over the chain for every aggregate (see gex.aggregate_all).
    agg = aggregate_all(snap)
    by_strike = agg.by_strike
    if not by_strike:
        return _empty_levels(snap)

    # Build the net-GEX evaluator once; the profile grid and the bisection
    # refinement of Zero Gamma share the exact same Black-Scholes basis.
    net_fn = make_net_gex_fn(snap)
    profile = gamma_profile(snap, width=profile_width, steps=profile_steps, net_fn=net_fn)
    zero_gamma = find_zero_gamma(profile, snap.spot, net_fn=net_fn)

    positive_nodes = sorted((s for s in by_strike if s.net_gex > 0), key=lambda s: s.net_gex, reverse=True)
    negative_nodes = sorted((s for s in by_strike if s.net_gex < 0), key=lambda s: s.net_gex)

    return GammaLevels(
        symbol=snap.symbol,
        spot=snap.spot,
        timestamp=snap.timestamp,
        net_gex=agg.net_gex,
        regime="positive" if agg.net_gex >= 0 else "negative",
        zero_gamma=zero_gamma,
        volatility_trigger=_volatility_trigger(by_strike, snap.spot, zero_gamma),
        call_wall=_call_wall(by_strike, snap.spot),
        put_wall=_put_wall(by_strike, snap.spot),
        absolute_gamma=_absolute_gamma(by_strike),
        hedge_wall=_hedge_wall(by_strike),
        top_positive_nodes=positive_nodes[:top_n],
        top_negative_nodes=negative_nodes[:top_n],
        by_strike=by_strike,
        by_expiry=agg.by_expiry,
        zero_dte_net_gex=agg.zero_dte_net_gex,
        zero_dte_share=(agg.zero_dte_abs_gex / agg.total_abs_gex) if agg.total_abs_gex else 0.0,
    )
