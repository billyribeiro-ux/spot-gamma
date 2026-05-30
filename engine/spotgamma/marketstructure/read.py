"""Assemble the live market-structure read from all free data sources.

Orchestration only: fetch each free input, build per-signal scores (signals.py),
and compose (composite.py). Each fetch is independently guarded so a single
unavailable feed degrades the read rather than failing it (§5 graceful
degradation). The gamma inputs are passed in by the caller (the API already has
the computed levels) so this module doesn't depend on a chain source.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

from . import signals as S
from .composite import RegimeRead, compose


class MarketStructure(NamedTuple):
    read: RegimeRead
    inputs: dict[str, float | None]  # raw observations, for display/debugging
    unavailable: list[str]  # feeds that failed (degraded gracefully)
    # §6 context (dispersion/tilt — NOT part of the RORO direction):
    event_risk: dict | None = None  # {events, score, label}
    seasonality: dict | None = None  # {factors, tilt, label}
    gaps: dict | None = None  # {today_gap_pct, today_bucket, today_fill_probability, buckets}


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

    # Breadth (§7) — self-computed from constituent closes; a directional-health
    # signal that joins the RORO sum. Skipped (graceful) if the fetch fails.
    bsig, _berr = _safe(_breadth_signal)
    if bsig is not None:
        sigs.append(bsig)
        inputs["breadth_pct_above_200dma"] = bsig.value
    else:
        unavailable.append("breadth")

    ratio = (vix / vix3m) if (vix and vix3m) else 1.0
    vr = S.vol_regime(vix or 20.0, ratio, vvix or 85.0)

    read = compose(sigs, vol_regime_label=vr, net_gex=net_gex, spot=spot, zero_gamma=zero_gamma)

    # §6 context (dispersion/tilt — computed from the date + OHLC, not the RORO).
    event_ctx, season_ctx, gap_ctx = _context_signals(unavailable)

    return MarketStructure(
        read=read,
        inputs=inputs,
        unavailable=unavailable,
        event_risk=event_ctx,
        seasonality=season_ctx,
        gaps=gap_ctx,
    )


def _breadth_signal():
    """Live breadth signal from the constituent universe (raises on failure)."""
    from .breadth import breadth_signal, compute_breadth
    from .feeds import fetch_constituent_closes

    closes = fetch_constituent_closes()
    if not closes:
        raise RuntimeError("no constituent data")
    sig = breadth_signal(compute_breadth(closes))
    if sig is None:
        raise RuntimeError("insufficient breadth history")
    return sig


def _context_signals(unavailable: list[str]) -> tuple[dict | None, dict | None, dict | None]:
    """Event-risk, seasonality, and gap context (each degrades independently)."""
    from .calendar import event_risk, seasonality
    from .feeds import load_scheduled_events

    today = datetime.now(UTC).date()

    er = event_risk(today, load_scheduled_events())
    event_ctx = {"events": er.events, "score": er.score, "label": er.label}

    se = seasonality(today)
    season_ctx = {"factors": se.factors, "tilt": se.tilt, "label": se.label}

    gap_ctx, _gap_err = _safe(_gap_context)
    if gap_ctx is None:
        unavailable.append("gaps")

    return event_ctx, season_ctx, gap_ctx


def _gap_context() -> dict:
    from .feeds import live_gap_stats

    gs = live_gap_stats()
    return {
        "today_gap_pct": gs.today_gap_pct,
        "today_bucket": gs.today_bucket,
        "today_fill_probability": gs.today_fill_probability,
        "buckets": [{"bucket": b.bucket, "count": b.count, "fill_rate": b.fill_rate} for b in gs.buckets],
    }
