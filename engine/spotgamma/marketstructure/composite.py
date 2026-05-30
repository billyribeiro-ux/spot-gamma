"""The composite market-structure regime read (§5 of MARKET_STRUCTURE.md).

Two transparent, separately-inspectable layers:
1. a Risk-On/Risk-Off (RORO) sub-score = documented-weight average of the
   available signals (each in [-1,+1], +1 = risk-off);
2. a dealer-gamma *modifier* multiplying the sub-score's actionability.

Weights are an explicit, documented prior (NOT fit to returns — that would overfit
a short sample); they reflect signal reliability per §5. Every number traces to
the methodology doc.
"""

from __future__ import annotations

from typing import NamedTuple

from .signals import Signal, gamma_modifier

# Documented weights (§5). The yield curve enters as a low-weight context flag,
# not a summed driver. Credit and vol carry the most weight (most reliable); the
# dollar the least (its equity sign flips). Weights sum to 1.0 over the signals
# actually present, so a missing feed degrades gracefully.
WEIGHTS: dict[str, float] = {
    "vix": 0.20,
    "term_structure": 0.20,
    "vvix": 0.10,
    "credit": 0.25,
    "dollar": 0.10,
    "yield_curve": 0.05,
    "gamma_sign": 0.10,
}


class RegimeRead(NamedTuple):
    """The finished composite, with every component left visible (§5 honesty rule)."""

    roro_score: float  # [-1, +1], +1 = risk-off (weighted avg of signals)
    gamma_modifier: float  # [0.5, 1.5] actionability multiplier
    regime_score: float  # roro_score * gamma_modifier, clamped to [-1.5, 1.5]
    bias: str  # "risk-on" | "neutral" | "risk-off"
    vol_regime: str  # "calm" | "normal" | "stressed" | "crisis"
    flip_transition_risk: bool  # spot within ~1% of zero-gamma
    signals: list[Signal]  # every component, for display
    divergence: bool  # signals disagree (an instability warning, §5)


def _bias(score: float) -> str:
    if score >= 0.33:
        return "risk-off"
    if score <= -0.33:
        return "risk-on"
    return "neutral"


def compose(
    signals: list[Signal],
    *,
    vol_regime_label: str,
    net_gex: float,
    spot: float,
    zero_gamma: float | None,
) -> RegimeRead:
    """Combine per-signal scores + the gamma gate into the composite read.

    ``signals`` may omit any signal whose feed was unavailable; weights are
    renormalized over what's present so the score degrades gracefully.
    """
    # Gamma also contributes a directional term (negative gamma = risk-off) at the
    # documented "gamma_sign" weight, on top of acting as the actionability gate.
    negative_regime = net_gex < 0 or (zero_gamma is not None and spot < zero_gamma)
    gamma_dir = 1.0 if negative_regime else -1.0

    weighted = 0.0
    total_w = 0.0
    for sig in signals:
        w = WEIGHTS.get(sig.key, 0.0)
        weighted += w * sig.score
        total_w += w
    # add the gamma directional term
    weighted += WEIGHTS["gamma_sign"] * gamma_dir
    total_w += WEIGHTS["gamma_sign"]

    roro = weighted / total_w if total_w else 0.0

    modifier = gamma_modifier(net_gex, spot, zero_gamma)
    regime_score = max(-1.5, min(1.5, roro * modifier))

    flip_risk = zero_gamma is not None and spot > 0 and abs(spot - zero_gamma) / spot < 0.01

    # divergence: at least one signal disagrees in sign with the consensus
    nonzero = [s.score for s in signals if abs(s.score) > 0.2]
    divergence = bool(nonzero) and not (all(v > 0 for v in nonzero) or all(v < 0 for v in nonzero))

    return RegimeRead(
        roro_score=roro,
        gamma_modifier=modifier,
        regime_score=regime_score,
        bias=_bias(roro),
        vol_regime=vol_regime_label,
        flip_transition_risk=flip_risk,
        signals=signals,
        divergence=divergence,
    )
