"""The composite market-structure regime read (§5 of MARKET_STRUCTURE.md).

Two transparent, separately-inspectable layers:
1. a Risk-On/Risk-Off (RORO) sub-score = documented-weight average of the
   available signals (each in [-1,+1], +1 = risk-off);
2. a dealer-gamma *modifier* that scales **actionability/conviction**, not the
   signed direction — deep negative gamma (trending) amplifies conviction; deep
   positive gamma (pinned) dampens it.

Crucially the modifier does NOT flip or amplify the *sign* of the RORO score
(that would make negative gamma read "more risk-on" in a calm tape, which is
nonsensical). The signed regime read stays the RORO sign; the modifier produces a
separate ``actionability`` figure. Weights are an explicit, documented prior (NOT
fit to returns); they match the §5 table exactly.
"""

from __future__ import annotations

from typing import NamedTuple

from .signals import Signal, gamma_modifier

# Documented weights (§5 table). Must match the doc — see test_weights_match_doc.
# The yield curve is a *context flag*: weight 0.0, displayed but NOT summed (it's
# a slow recession prior with the wrong sign intraday — see §3.1 / the 2022-24
# inversion-without-recession counterexample). Gamma enters the RORO sum once via
# its sign at 0.15; it ALSO drives the actionability modifier (the dual role is
# documented in §4/§5 — the additive term is gamma's directional vote, the
# modifier is its volatility-regime gate; we keep both but never let the modifier
# touch the signed score, avoiding the compounding §5(b) warns about).
WEIGHTS: dict[str, float] = {
    "vix": 0.18,
    "term_structure": 0.18,
    "vvix": 0.08,
    "credit": 0.22,
    "breadth": 0.15,
    "put_call": 0.05,
    "dollar": 0.08,
    "yield_curve": 0.00,  # context flag — displayed, not summed
    "gamma_sign": 0.06,
}

# Keys whose signal is shown for context but excluded from the weighted RORO sum.
_CONTEXT_ONLY = frozenset({"yield_curve"})


class RegimeRead(NamedTuple):
    """The finished composite, with every component left visible (§5 honesty rule)."""

    roro_score: float  # [-1, +1], +1 = risk-off (signed direction; weighted avg)
    gamma_modifier: float  # [0.5, 1.5] conviction multiplier (pinned..trending)
    actionability: float  # [0, 1.5] = |roro| * modifier — how strongly to act
    regime_score: float  # signed conviction = sign(roro) * actionability, in [-1.5, 1.5]
    bias: str  # "risk-on" | "neutral" | "risk-off" (from roro_score)
    vol_regime: str  # "calm" | "normal" | "stressed" | "crisis"
    flip_transition_risk: bool  # spot within ~1% of zero-gamma
    signals: list[Signal]  # every component (incl. context-only), for display
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
    net_gex: float | None = None,
    spot: float | None = None,
    zero_gamma: float | None = None,
    weights: dict[str, float] | None = None,
) -> RegimeRead:
    """Combine per-signal scores + the gamma gate into the composite read.

    ``signals`` may omit any signal whose feed was unavailable; weights are
    renormalized over what's present so the score degrades gracefully. Context-only
    signals (e.g. the yield curve) are kept for display but excluded from the sum.
    When gamma is unavailable (``net_gex``/``spot`` is None — e.g. the chain feed
    is down) the gamma directional vote is excluded and the modifier is a neutral
    1.0, so the macro/vol read still computes.

    ``weights`` defaults to the documented §5 prior (:data:`WEIGHTS`); a learned,
    out-of-sample-validated weight set may be passed in (see
    :mod:`spotgamma.learning`), but the prior remains the anchor and the default.
    """
    w_map = weights or WEIGHTS
    # Explicit narrowing (not a boolean flag) so the gamma branch is type-proven:
    # inside this block net_gex/spot are float, never None.
    weighted = 0.0
    total_w = 0.0
    for sig in signals:
        if sig.key in _CONTEXT_ONLY:
            continue  # displayed, not summed
        w = w_map.get(sig.key, 0.0)
        weighted += w * sig.score
        total_w += w

    modifier = 1.0  # neutral when gamma data is unavailable
    flip_risk = False
    if net_gex is not None and spot is not None:
        # Gamma's directional vote (negative gamma = risk-off) at the gamma_sign weight.
        negative_regime = net_gex < 0 or (zero_gamma is not None and spot < zero_gamma)
        gamma_w = w_map.get("gamma_sign", WEIGHTS["gamma_sign"])
        weighted += gamma_w * (1.0 if negative_regime else -1.0)
        total_w += gamma_w
        # The modifier scales *conviction*, never the sign. Deep negative gamma
        # (~1.5) amplifies how hard to act on whatever the RORO read is; deep
        # positive gamma (~0.5) dampens it (pinned/mean-reverting fades extremes).
        modifier = gamma_modifier(net_gex, spot, zero_gamma)
        flip_risk = zero_gamma is not None and spot > 0 and abs(spot - zero_gamma) / spot < 0.01

    roro = weighted / total_w if total_w else 0.0
    actionability = abs(roro) * modifier
    sign = 1.0 if roro > 0 else (-1.0 if roro < 0 else 0.0)
    regime_score = max(-1.5, min(1.5, sign * actionability))

    # Divergence: among signals with a meaningful read, do they disagree in sign?
    # Requires at least two opinionated signals (a lone signal can't "diverge").
    # Context-only signals (yield curve) are excluded — mirroring the RORO sum —
    # so a slow recession prior can't fabricate or mask a divergence warning.
    opinions = [s.score for s in signals if s.key not in _CONTEXT_ONLY and abs(s.score) > 0.2]
    divergence = len(opinions) >= 2 and not (all(v > 0 for v in opinions) or all(v < 0 for v in opinions))

    return RegimeRead(
        roro_score=roro,
        gamma_modifier=modifier,
        actionability=actionability,
        regime_score=regime_score,
        bias=_bias(roro),
        vol_regime=vol_regime_label,
        flip_transition_risk=flip_risk,
        signals=signals,
        divergence=divergence,
    )
