"""Shared value normalization for vendor adapters.

Vendors disagree on implied-volatility units: Schwab/ORATS emit percent points
(``16.0`` = 16%), most others emit a decimal (``0.16``). Rather than special-case
each adapter, every source routes IV through :func:`normalize_iv`, which also
drops non-numeric and sentinel (-999/NaN) values.
"""

from __future__ import annotations

# Index/ETF implied vol is essentially never above 300% as a decimal, so a value
# that large is almost certainly expressed in percent points -> divide by 100.
_PERCENT_THRESHOLD = 3.0


def normalize_iv(value: object) -> float | None:
    """Return IV as a decimal (e.g. 0.16), or None if absent/invalid/sentinel."""
    if value is None:
        return None
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None  # guards stray "NaN"/string values
    if v != v or v <= 0:  # NaN or non-positive (incl. -999 sentinels)
        return None
    return v / 100.0 if v > _PERCENT_THRESHOLD else v
