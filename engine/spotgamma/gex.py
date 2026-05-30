"""Dollar gamma exposure: contract-level calculation and aggregation.

Sign convention (documented in docs/METHODOLOGY.md): we assume dealers are
**long calls and short puts**, so call gamma contributes positive GEX and put
gamma contributes negative GEX. This is an inference from public open interest,
not observed dealer positioning.

Contract-level dollar gamma per 1% move::

    GEX_i = gamma_i * OI_i * multiplier * spot**2 * 0.01

The result is the dollar notional of underlying dealers must trade to stay
delta-neutral for a 1% move in spot.
"""
from __future__ import annotations

from collections import defaultdict

from .greeks import bs_gamma
from .models import ChainSnapshot, ExpiryGamma, OptionContract, OptionType, StrikeGamma

# Fallback IV used only when a source supplies neither gamma nor IV. A flat
# assumption is crude but keeps a contract from silently dropping to zero
# weight; the methodology doc flags this as a data-quality fallback.
_FALLBACK_IV = 0.20


def _contract_gamma(c: OptionContract, snap: ChainSnapshot, spot: float) -> float:
    """Per-share gamma for a contract at a given spot.

    Prefers source gamma when evaluating at the snapshot spot; recomputes via
    Black-Scholes for any other spot (profile mode) or when source gamma is
    missing.
    """
    at_snapshot = spot == snap.spot
    if at_snapshot and c.gamma is not None:
        return c.gamma
    iv = c.implied_volatility if c.implied_volatility else _FALLBACK_IV
    return bs_gamma(spot, c.strike, snap.dte(c.expiration), iv, snap.risk_free_rate)


def contract_gex(c: OptionContract, snap: ChainSnapshot, spot: float | None = None) -> float:
    """Signed dollar gamma exposure for one contract."""
    s = snap.spot if spot is None else spot
    gamma = _contract_gamma(c, snap, s)
    magnitude = gamma * c.open_interest * snap.multiplier * s * s * 0.01
    return magnitude if c.option_type is OptionType.CALL else -magnitude


def aggregate_by_strike(snap: ChainSnapshot, spot: float | None = None) -> list[StrikeGamma]:
    """Sum signed GEX into call/put buckets per strike, sorted ascending."""
    calls: dict[float, float] = defaultdict(float)
    puts: dict[float, float] = defaultdict(float)
    for c in snap.contracts:
        g = contract_gex(c, snap, spot)
        if c.option_type is OptionType.CALL:
            calls[c.strike] += g
        else:
            puts[c.strike] += g
    strikes = sorted(set(calls) | set(puts))
    return [StrikeGamma(strike=k, call_gex=calls.get(k, 0.0), put_gex=puts.get(k, 0.0)) for k in strikes]


def aggregate_by_expiry(snap: ChainSnapshot, spot: float | None = None) -> list[ExpiryGamma]:
    """Sum signed net GEX per expiration, sorted by date."""
    net: dict = defaultdict(float)
    for c in snap.contracts:
        net[c.expiration] += contract_gex(c, snap, spot)
    out = [
        ExpiryGamma(expiration=exp, net_gex=val, dte_days=(exp - snap.timestamp.date()).days)
        for exp, val in net.items()
    ]
    out.sort(key=lambda e: e.expiration)
    return out


def net_gex(snap: ChainSnapshot, spot: float | None = None) -> float:
    """Total signed dollar gamma across the whole chain."""
    return sum(contract_gex(c, snap, spot) for c in snap.contracts)
