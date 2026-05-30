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

import math
from collections import defaultdict
from datetime import date
from typing import NamedTuple

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
    at_snapshot = math.isclose(spot, snap.spot, rel_tol=1e-9)
    if at_snapshot and c.gamma is not None:
        return c.gamma
    iv = c.implied_volatility if c.implied_volatility else _FALLBACK_IV
    return bs_gamma(spot, c.strike, snap.dte(c.expiration), iv, snap.risk_free_rate, snap.dividend_yield)


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
    out = [ExpiryGamma(expiration=exp, net_gex=val, dte_days=snap.days_to_expiry(exp)) for exp, val in net.items()]
    out.sort(key=lambda e: e.expiration)
    return out


def net_gex(snap: ChainSnapshot, spot: float | None = None) -> float:
    """Total signed dollar gamma across the whole chain."""
    return sum(contract_gex(c, snap, spot) for c in snap.contracts)


class ChainAggregates(NamedTuple):
    """Everything :func:`spotgamma.levels.compute_levels` needs, from one pass."""

    by_strike: list[StrikeGamma]
    by_expiry: list[ExpiryGamma]
    net_gex: float
    total_abs_gex: float
    zero_dte_net_gex: float
    zero_dte_abs_gex: float


def aggregate_all(snap: ChainSnapshot, spot: float | None = None) -> ChainAggregates:
    """Compute every chain aggregate in a single pass.

    The naive approach calls ``contract_gex`` 4–6× per contract (by-strike,
    by-expiry, net, total-abs, and the two 0DTE sums). On a 30k-contract index
    chain that is >100k redundant gamma evaluations per request; folding them
    into one loop computes each contract's GEX exactly once.
    """
    calls: dict[float, float] = defaultdict(float)
    puts: dict[float, float] = defaultdict(float)
    by_exp: dict[date, float] = defaultdict(float)
    net = total_abs = zdte_net = zdte_abs = 0.0
    session = snap.session_date

    for c in snap.contracts:
        g = contract_gex(c, snap, spot)
        if c.option_type is OptionType.CALL:
            calls[c.strike] += g
        else:
            puts[c.strike] += g
        by_exp[c.expiration] += g
        net += g
        total_abs += abs(g)
        if c.expiration == session:
            zdte_net += g
            zdte_abs += abs(g)

    by_strike = [
        StrikeGamma(strike=k, call_gex=calls.get(k, 0.0), put_gex=puts.get(k, 0.0))
        for k in sorted(set(calls) | set(puts))
    ]
    by_expiry = sorted(
        (ExpiryGamma(expiration=e, net_gex=v, dte_days=snap.days_to_expiry(e)) for e, v in by_exp.items()),
        key=lambda e: e.expiration,
    )
    return ChainAggregates(by_strike, by_expiry, net, total_abs, zdte_net, zdte_abs)
