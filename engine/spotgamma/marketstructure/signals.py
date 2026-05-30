"""Per-signal regime scoring — the normalization layer.

Each function turns a raw market observation into a documented, bounded signal
following ``docs/MARKET_STRUCTURE.md`` (§2-4). Every threshold here cites that
doc; nothing is invented at the code layer. All functions are pure so they're
unit-tested without the network.

Convention: a signal's ``score`` is in ``[-1, +1]`` where **+1 = maximally
risk-off** and **-1 = maximally risk-on**, so signals compose by a simple
weighted average (see ``composite.py``). Each also carries a human ``label`` and
the raw ``value`` for display.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

Bias = Literal["risk-on", "neutral", "risk-off"]


class Signal(NamedTuple):
    key: str
    label: str  # short regime label, e.g. "elevated", "backwardation"
    value: float  # the raw observation (for display)
    score: float  # [-1, +1], +1 = risk-off
    detail: str  # one-line explanation

    @property
    def bias(self) -> Bias:
        if self.score >= 0.33:
            return "risk-off"
        if self.score <= -0.33:
            return "risk-on"
        return "neutral"


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _lerp_score(value: float, calm: float, crisis: float) -> float:
    """Map a value onto [-1, +1] linearly: ``calm`` -> -1, ``crisis`` -> +1."""
    if crisis == calm:
        return 0.0
    return _clamp(2.0 * (value - calm) / (crisis - calm) - 1.0)


# --- Volatility (§2) -------------------------------------------------------
def vix_signal(vix: float) -> Signal:
    """VIX level -> regime score. Bands per §2.1 (practitioner convention)."""
    if vix < 15:
        label = "calm"
    elif vix < 20:
        label = "normal"
    elif vix < 30:
        label = "elevated"
    elif vix < 40:
        label = "fear"
    else:
        label = "crisis"
    # 12 (calm) -> -1, 30 (fear) -> +1, so the ~20 long-run mean reads ~neutral
    # and "elevated" (20-30) reads mildly risk-off.
    score = _lerp_score(vix, calm=12.0, crisis=30.0)
    return Signal("vix", label, vix, score, f"VIX {vix:.1f} — {label}")


def term_structure_signal(vix: float, vix3m: float) -> Signal:
    """VIX/VIX3M ratio -> regime. <1 contango (calm), >1 backwardation (§2.2)."""
    if vix3m <= 0:
        return Signal("term_structure", "n/a", 0.0, 0.0, "VIX3M unavailable")
    ratio = vix / vix3m
    label = "backwardation" if ratio >= 1.0 else "contango"
    # 0.85 (healthy contango) -> -1, 1.10 (deep backwardation) -> +1
    score = _lerp_score(ratio, calm=0.85, crisis=1.10)
    return Signal("term_structure", label, ratio, score, f"VIX/VIX3M {ratio:.3f} — {label}")


def vvix_signal(vvix: float, vix: float) -> Signal:
    """VVIX -> fragility. Value is the VVIX/VIX divergence, not the level (§2.3).

    Low-and-fragile = elevated VVIX while VIX is subdued. We score the VVIX/VIX
    ratio relative to its rough normal (~6) so a high ratio at low VIX reads as
    risk-off even when VIX itself looks calm.
    """
    if vix <= 0:
        return Signal("vvix", "n/a", vvix, 0.0, "VIX unavailable")
    ratio = vvix / vix
    label = "fragile" if ratio >= 7.0 else ("calm" if ratio < 5.0 else "normal")
    # ratio 4 (stable) -> -1, ratio 9 (very fragile) -> +1
    score = _lerp_score(ratio, calm=4.0, crisis=9.0)
    return Signal("vvix", label, vvix, score, f"VVIX/VIX {ratio:.1f} — {label}")


def vol_regime(vix: float, ratio: float, vvix_ratio: float) -> str:
    """Transparent calm/normal/stressed/crisis label from §2.4's matrix."""
    backwardation = ratio >= 1.0
    if vix > 30:
        return "crisis" if backwardation else "stressed"
    if vix > 20:
        return "stressed" if backwardation else "normal"
    # VIX < 20
    if backwardation:
        return "stressed"
    return "normal" if vvix_ratio >= 7.0 else "calm"


# --- Macro / cross-asset (§3) ---------------------------------------------
def yield_curve_signal(spread_2s10s: float) -> Signal:
    """2s10s spread -> recession-prior context flag (§3.1).

    Held at low weight in the composite (it's a slow prior, wrong sign intraday);
    inversion (<0) reads mildly risk-off.
    """
    if spread_2s10s < 0:
        label, score = "inverted", 0.5
    elif spread_2s10s < 0.5:
        label, score = "flat", 0.2
    elif spread_2s10s > 1.5:
        label, score = "steep", -0.3
    else:
        label, score = "normal", -0.1
    return Signal("yield_curve", label, spread_2s10s, score, f"2s10s {spread_2s10s:+.2f} — {label}")


def credit_signal(hy_oas: float, hy_oas_20d_ago: float | None = None) -> Signal:
    """HY OAS level + rate-of-change -> risk score (§3.3).

    Level bands set the base; a fast widening off a low base adds risk-off even
    when the level is still numerically low (rate-of-change > level).
    """
    # 300bp (3.0, tight) -> -1, 800bp (8.0, stress) -> +1
    base = _lerp_score(hy_oas, calm=3.0, crisis=8.0)
    roc = 0.0
    if hy_oas_20d_ago and hy_oas_20d_ago > 0:
        change = (hy_oas - hy_oas_20d_ago) / hy_oas_20d_ago
        roc = _clamp(change, -0.3, 0.3)  # +30% in 20d -> +0.3 risk-off nudge
    score = _clamp(base + roc)
    if hy_oas < 3.0:
        label = "tight"
    elif hy_oas < 5.0:
        label = "normal"
    elif hy_oas < 6.0:
        label = "caution"
    else:
        label = "stress"
    return Signal("credit", label, hy_oas, score, f"HY OAS {hy_oas:.2f}% — {label}")


def dollar_signal(dxy: float, dxy_200dma: float | None, dxy_20d_change_pct: float | None) -> Signal:
    """DXY trend + rate-of-change -> modest risk score (§3.2).

    The dollar's equity sign flips with the regime (Dollar Smile), so we score
    only *rapid* strength as a mild headwind and keep the weight low. A sustained
    move above the 200-DMA plus fast appreciation reads mildly risk-off.
    """
    above_trend = dxy_200dma is not None and dxy > dxy_200dma
    roc = dxy_20d_change_pct or 0.0
    # fast appreciation (>+3% in 20d) is the equity-negative event
    score = _clamp(roc / 3.0)  # +3% -> +1 before trend gating
    if not above_trend:
        score *= 0.5  # below the 200-DMA, dollar strength is less of a headwind
    label = "strengthening" if score > 0.2 else ("weakening" if score < -0.2 else "neutral")
    return Signal("dollar", label, dxy, _clamp(score), f"DXY {dxy:.1f} — {label}")


# --- Dealer gamma gate (§4) -----------------------------------------------
def gamma_modifier(net_gex: float, spot: float, zero_gamma: float | None) -> float:
    """Map dealer gamma to an actionability multiplier in [0.5, 1.5] (§4/§5).

    Deep positive gamma (pinned, mean-reverting) dampens conviction -> 0.5;
    deep negative gamma (trending, amplified) -> 1.5; near the flip -> ~1.0 with a
    transition-risk flag handled by the caller.
    """
    negative_regime = net_gex < 0 or (zero_gamma is not None and spot < zero_gamma)
    # distance to flip as a fraction of spot, capped — 0 at the flip, 1 at >=5% away
    dist = min(abs(spot - zero_gamma) / spot, 0.05) / 0.05 if (zero_gamma and spot > 0) else 1.0
    if negative_regime:
        return 1.0 + 0.5 * dist  # 1.0 -> 1.5
    return 1.0 - 0.5 * dist  # 1.0 -> 0.5
