"""Assemble the live market-structure read from all free data sources.

Orchestration only: fetch each free input, build per-signal scores (signals.py),
and compose (composite.py). Each fetch is independently guarded so a single
unavailable feed degrades the read rather than failing it (§5 graceful
degradation). The gamma inputs are passed in by the caller (the API already has
the computed levels) so this module doesn't depend on a chain source.
"""

from __future__ import annotations

from typing import NamedTuple

from . import signals as S
from .composite import RegimeRead, compose


class MarketStructure(NamedTuple):
    read: RegimeRead
    inputs: dict[str, float | None]  # raw observations, for display/debugging
    unavailable: list[str]  # feeds that failed (degraded gracefully)


def _safe(fn, *args):
    try:
        return fn(*args), None
    except Exception as e:
        return None, f"{e}"


def build_market_structure(
    *, net_gex: float | None = None, spot: float | None = None, zero_gamma: float | None = None
) -> MarketStructure:
    """Fetch every free signal and compose the regime read (graceful on failure).

    Gamma inputs are optional: when the chain feed is unavailable, the macro/vol
    read still computes (the gamma vote/gate are simply excluded — see compose).
    """
    from .fred import fetch_series, latest
    from .quotes import fetch_quote

    inputs: dict[str, float | None] = {}
    unavailable: list[str] = []

    def q(ticker: str, key: str) -> float | None:
        quote, err = _safe(fetch_quote, ticker)
        if err or quote is None:
            unavailable.append(key)
            return None
        inputs[key] = quote.price
        return quote.price

    def f(series_id: str, key: str) -> float | None:
        pts, err = _safe(fetch_series, series_id)
        if err or not pts:
            unavailable.append(key)
            return None
        val = latest(pts).value
        inputs[key] = val
        return val

    vix = q("^VIX", "vix")
    vix3m = q("^VIX3M", "vix3m")
    vvix = q("^VVIX", "vvix")
    dxy = q("DX-Y.NYB", "dxy")
    hy = f("BAMLH0A0HYM2", "hy_oas")
    spread = f("T10Y2Y", "spread_2s10s")

    sigs: list[S.Signal] = []
    if vix is not None:
        sigs.append(S.vix_signal(vix))
    if vix is not None and vix3m is not None:
        sigs.append(S.term_structure_signal(vix, vix3m))
    if vvix is not None and vix is not None:
        sigs.append(S.vvix_signal(vvix, vix))
    if hy is not None:
        sigs.append(S.credit_signal(hy))
    if spread is not None:
        sigs.append(S.yield_curve_signal(spread))
    if dxy is not None:
        sigs.append(S.dollar_signal(dxy, None, None))

    ratio = (vix / vix3m) if (vix and vix3m) else 1.0
    vr = S.vol_regime(vix or 20.0, ratio, vvix or 85.0)

    read = compose(sigs, vol_regime_label=vr, net_gex=net_gex, spot=spot, zero_gamma=zero_gamma)
    return MarketStructure(read=read, inputs=inputs, unavailable=unavailable)
