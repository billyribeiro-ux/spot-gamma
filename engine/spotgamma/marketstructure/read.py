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
    # §7 learned overlay (only when a validated model artifact is present):
    learned: dict | None = None  # {adopt_weights, adopt_tilt, tilt_fwd_return, calibration, ...}


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
    from .fred import fetch_series
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
        val = pts[-1].value  # fetch_series is chronological; pts is non-empty here
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
        sigs.append(_dollar_signal(dxy))

    # Breadth (§7) — self-computed from constituent closes; a directional-health
    # signal that joins the RORO sum. Skipped (graceful) if the fetch fails.
    bsig, _berr = _safe(_breadth_signal)
    if bsig is not None:
        sigs.append(bsig)
        inputs["breadth_pct_above_200dma"] = bsig.value
    else:
        unavailable.append("breadth")

    # Put/call (§7) — contrarian, z-scored sentiment proxy from chain volumes.
    # Abstains (score 0) until the rolling history has >=20 obs; skipped
    # (graceful) if the option-chain fetch fails.
    pcsig, _pcerr = _safe(_put_call_signal)
    if pcsig is not None:
        sigs.append(pcsig)
        inputs["put_call_ratio"] = pcsig.value
    else:
        unavailable.append("put_call")

    ratio = (vix / vix3m) if (vix and vix3m) else 1.0
    vr = S.vol_regime(vix or 20.0, ratio, vvix or 85.0)

    # §7 learned model: use calibrated weights only if they were adopted OOS
    # (else the documented §5 prior), and surface the validated overlay.
    model = _load_model_safe()
    weights = _effective_weights(model)
    read = compose(sigs, vol_regime_label=vr, net_gex=net_gex, spot=spot, zero_gamma=zero_gamma, weights=weights)
    learned = _learned_overlay(model, sigs, read.roro_score)

    # §6 context (dispersion/tilt — computed from the date + OHLC, not the RORO).
    event_ctx, season_ctx, gap_ctx = _context_signals(unavailable)

    return MarketStructure(
        read=read,
        inputs=inputs,
        unavailable=unavailable,
        event_risk=event_ctx,
        seasonality=season_ctx,
        gaps=gap_ctx,
        learned=learned,
    )


def _load_model_safe() -> dict | None:
    """Load the learned artifact if present (never raises — absent model is normal)."""
    try:
        from ..learning.store import load_model

        return load_model()
    except Exception:
        return None


def _effective_weights(model: dict | None) -> dict | None:
    from ..learning.model import effective_weights

    return effective_weights(model) if model else None


def _learned_overlay(model: dict | None, sigs: list, roro_score: float) -> dict | None:
    """The validated learned overlay for display: tilt + calibration bucket.

    Returns None when no model artifact exists. The tilt forward-return estimate
    is only populated when the tilt was adopted OOS; the calibration bucket is the
    empirical forward-return cell the current composite score falls into.
    """
    if not model:
        return None
    from ..learning.model import apply_tilt, calibration_lookup

    scores = {s.key: s.score for s in sigs}
    v = model.get("validation", {})
    return {
        "horizon": model.get("horizon"),
        "trained_through": model.get("trained_through"),
        "adopt_weights": v.get("adopt_weights"),
        "adopt_tilt": v.get("adopt_tilt"),
        "oos_ic": v.get("calibrated_oos_ic") if v.get("adopt_weights") else v.get("prior_oos_ic"),
        "tilt_fwd_return": apply_tilt(model, scores),  # None unless tilt adopted
        "calibration": calibration_lookup(model, roro_score),
    }


_DOLLAR_MA_WINDOW = 200
_DOLLAR_ROC_WINDOW = 20


def _dollar_signal(dxy: float):
    """Dollar signal with its trend filter wired (200-DMA + 20-day rate-of-change).

    The signal is direction/momentum-based (§3.2): without the 200-DMA and RoC it
    is permanently neutral. We fetch DXY daily closes and compute both, point-in-
    time (trailing only); if the history fetch fails we degrade to the bare level
    (neutral), never crashing the read. Mirrors the backtest's dollar features so
    the live read and the §7 calibration agree.
    """
    from .quotes import fetch_daily_closes

    closes, _err = _safe(fetch_daily_closes, "DX-Y.NYB")
    ma200 = roc_pct = None
    if closes:
        if len(closes) >= _DOLLAR_MA_WINDOW:
            ma200 = sum(closes[-_DOLLAR_MA_WINDOW:]) / _DOLLAR_MA_WINDOW
        if len(closes) > _DOLLAR_ROC_WINDOW:
            past = closes[-(_DOLLAR_ROC_WINDOW + 1)]
            roc_pct = (dxy / past - 1.0) * 100.0 if past else None
    return S.dollar_signal(dxy, ma200, roc_pct)


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


def _put_call_signal():
    """Live put/call sentiment signal from chain volumes (raises on failure).

    Sums put vs call option volumes across a liquid basket, persists the daily
    ratio to a rolling history, and z-scores it. With <20 observations the signal
    correctly abstains (score 0) — the documented insufficient-history behavior.
    """
    from .feeds import fetch_put_call_volumes, put_call_baseline, update_put_call_history
    from .putcall import PutCallStats, put_call_proxy, put_call_signal, zscore

    put_vol, call_vol = fetch_put_call_volumes()
    ratio = put_call_proxy(put_vol, call_vol)
    if ratio is None:
        raise RuntimeError("no put/call volume")
    # Z-score today's ratio against its PRIOR baseline (excluding today) so the
    # observation isn't scored against a window that already contains it, then
    # persist today for future baselines.
    baseline = put_call_baseline()
    z, pct = zscore(ratio, baseline)
    update_put_call_history(ratio)
    return put_call_signal(PutCallStats(ratio=ratio, z=z, percentile=pct))


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
        "buckets": [{"bucket": b.bucket, "count": b.n, "fill_rate": b.fill_rate} for b in gs.buckets],
    }
