"""Shared value normalization for vendor adapters.

Vendors disagree on implied-volatility units: Schwab/ORATS emit percent points
(``16.0`` = 16%), most others emit a decimal (``0.16``). The vendor's unit is
*known per adapter*, so each source declares it explicitly via the ``unit``
argument and the conversion is deterministic. An ``"auto"`` magnitude heuristic
remains only as a fallback for callers that genuinely don't know the unit.
:func:`normalize_iv` also drops non-numeric and sentinel (-999/NaN) values.
"""

from __future__ import annotations

from typing import Literal

IVUnit = Literal["auto", "percent", "decimal"]

# Index/ETF implied vol is essentially never above 300% as a decimal, so a value
# that large is almost certainly expressed in percent points -> divide by 100.
# Used only for the "auto" fallback; prefer an explicit unit.
_PERCENT_THRESHOLD = 3.0


def normalize_iv(value: object, unit: IVUnit = "auto") -> float | None:
    """Return IV as a decimal (e.g. 0.16), or None if absent/invalid/sentinel.

    ``unit`` declares the vendor's IV unit deterministically (preferred):
    ``"percent"`` always divides by 100, ``"decimal"`` never does. ``"auto"``
    (default) falls back to the magnitude heuristic — which can misclassify a
    genuine >300% decimal IV or a sub-3% percent-point IV, so adapters should pass
    their known unit rather than rely on it.
    """
    if value is None:
        return None
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None  # guards stray "NaN"/string values
    if v != v or v <= 0:  # NaN or non-positive (incl. -999 sentinels)
        return None
    if unit == "percent":
        return v / 100.0
    if unit == "decimal":
        return v
    return v / 100.0 if v > _PERCENT_THRESHOLD else v
