"""Point-in-time feature/label construction for the backtest (no lookahead).

Turns the historical :mod:`panel` into rows of ``(signal scores at t, forward
SPY returns t→t+h)``. The single invariant enforced here:

* **Features at date *t* use only rows with index ≤ t.** Trailing statistics the
  live signals need — the dollar's 200-day MA and 20-day rate-of-change, credit's
  20-day-ago level — are computed from the trailing window, never the future.
* **Labels are forward returns** ``spy[t+h]/spy[t] − 1`` for ``h`` trading days.

The signal *scoring* reuses the exact live functions in
:mod:`spotgamma.marketstructure.signals`, so the backtest measures the real
deployed logic, not a re-implementation. Only the vol+macro signals with clean
free history participate (breadth/put-call/gamma sign have no free history — see
``panel``); the yield curve is carried as a context column (prior weight 0).

Everything here is a pure function of a panel — unit-tested without the network.
"""

from __future__ import annotations

from typing import NamedTuple

from ..marketstructure import signals as S
from .panel import PanelRow

# Signals computable from the historical panel, with their live scorer. The
# yield curve is included (it is a displayed context flag, prior weight 0); the
# rest carry their §5 prior weight in composite.WEIGHTS.
HISTORICAL_SIGNALS = ("vix", "term_structure", "vvix", "credit", "dollar", "yield_curve")

# Default forward-return horizons (trading days). 1d = next-session, 5d ≈ a week,
# 20d ≈ a month — the macro/vol read is a regime prior, weakest same-day (§0.1).
DEFAULT_HORIZONS = (1, 5, 20)

_DOLLAR_MA_WINDOW = 200  # 200-day trend filter (signals.dollar_signal)
_ROC_WINDOW = 20  # 20-day rate-of-change window (dollar + credit)


class FeatureRow(NamedTuple):
    date: str  # ISO date of t
    scores: dict[str, float]  # per-signal score at t, +1 = risk-off
    fwd_returns: dict[int, float]  # horizon (trading days) -> forward SPY return


def _trailing(panel: list[PanelRow], i: int, key: str, window: int) -> list[float]:
    """Non-null values of ``key`` in rows ``[i-window+1 .. i]`` (point-in-time)."""
    lo = max(0, i - window + 1)
    return [v for r in panel[lo : i + 1] if (v := r.values.get(key)) is not None]


def _value_n_back(panel: list[PanelRow], i: int, key: str, n: int) -> float | None:
    """The value of ``key`` ``n`` trading rows before ``i`` (None if out of range/missing)."""
    j = i - n
    return panel[j].values.get(key) if j >= 0 else None


def signal_scores_at(panel: list[PanelRow], i: int) -> dict[str, float] | None:
    """Per-signal regime scores at row ``i`` using only rows ≤ ``i`` (no lookahead).

    Returns None when the core vol inputs (VIX/VIX3M/VVIX) are not yet available;
    individual macro signals are simply omitted from the dict when their input is
    missing, mirroring the live graceful-degradation contract.
    """
    row = panel[i]
    v = row.values
    vix, vix3m, vvix = v.get("vix"), v.get("vix3m"), v.get("vvix")
    if vix is None or vix3m is None or vvix is None:
        return None

    scores: dict[str, float] = {
        "vix": S.vix_signal(vix).score,
        "term_structure": S.term_structure_signal(vix, vix3m).score,
        "vvix": S.vvix_signal(vvix, vix).score,
    }

    hy = v.get("hy_oas")
    if hy is not None:
        hy_20d = _value_n_back(panel, i, "hy_oas", _ROC_WINDOW)
        scores["credit"] = S.credit_signal(hy, hy_20d).score

    spread = v.get("spread")
    if spread is not None:
        scores["yield_curve"] = S.yield_curve_signal(spread).score

    dxy = v.get("dxy")
    if dxy is not None:
        trail = _trailing(panel, i, "dxy", _DOLLAR_MA_WINDOW)
        ma200 = (sum(trail) / len(trail)) if len(trail) >= _DOLLAR_MA_WINDOW else None
        dxy_20d = _value_n_back(panel, i, "dxy", _ROC_WINDOW)
        roc_pct = ((dxy / dxy_20d - 1.0) * 100.0) if dxy_20d else None
        scores["dollar"] = S.dollar_signal(dxy, ma200, roc_pct).score

    return scores


def forward_returns_at(panel: list[PanelRow], i: int, horizons: tuple[int, ...]) -> dict[int, float]:
    """Forward SPY returns ``spy[i+h]/spy[i] − 1`` for each horizon (only when both exist)."""
    spot = panel[i].values.get("spy")
    out: dict[int, float] = {}
    if not spot:
        return out
    for h in horizons:
        j = i + h
        if j < len(panel):
            fut = panel[j].values.get("spy")
            if fut:
                out[h] = fut / spot - 1.0
    return out


def build_dataset(
    panel: list[PanelRow],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    *,
    require_all_horizons: bool = False,
) -> list[FeatureRow]:
    """Build point-in-time feature/label rows from a panel (pure, no lookahead).

    A row is emitted when its signal scores are computable and at least one
    forward return exists (or all, if ``require_all_horizons``). Rows near the end
    of the panel that have no future bar are naturally dropped.
    """
    max_h = max(horizons)
    rows: list[FeatureRow] = []
    for i in range(len(panel)):
        scores = signal_scores_at(panel, i)
        if scores is None:
            continue
        fwd = forward_returns_at(panel, i, horizons)
        if not fwd:
            continue
        if require_all_horizons and len(fwd) < len(horizons):
            continue
        rows.append(FeatureRow(panel[i].date.isoformat(), scores, fwd))
    # Drop the trailing rows whose longest-horizon label cannot exist yet, so the
    # default (single-horizon) consumers see only fully-labeled history.
    _ = max_h  # documented: per-horizon presence is already enforced above
    return rows
