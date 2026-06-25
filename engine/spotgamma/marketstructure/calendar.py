"""Calendar-derived signals: event risk (§6.3) and seasonality (§6.2).

Everything here is a pure function of the date (no network). Two hard rules from
the methodology:

* **Event risk gates *dispersion*, not direction** — a scheduled macro event
  raises the range of outcomes; it does not predict the sign.
* **Deterministic vs feed-required.** OPEX, triple-witching, an NFP *heuristic*,
  and NYSE holidays are computable from the date. FOMC / CPI / PCE / GDP are
  **never formula-faked** (§6.3) — their exact dates come from a maintained
  schedule file (``scheduled_events``), and are simply absent if not provided.

Seasonality is **shrunk hard and labeled** (§6.2): only turn-of-month (replicated,
with a mechanism) and a faint pre-holiday tilt feed the small seasonal score;
day-of-week / Santa / September / Sell-in-May are excluded from the return score.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple

# --- NYSE holidays (fixed + observed) -------------------------------------
# A small static set is honest and deterministic; full-history holiday tables
# (Good Friday etc.) can be layered later. These are the regular-closure dates.
_FIXED_HOLIDAYS = {
    (1, 1): "New Year's Day",
    (6, 19): "Juneteenth",
    (7, 4): "Independence Day",
    (12, 25): "Christmas",
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The ``n``-th ``weekday`` (Mon=0..Sun=6) of ``year``-``month`` (n>=1)."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def is_third_friday(d: date) -> bool:
    """Monthly options expiration (OPEX) — the 3rd Friday."""
    return d == _nth_weekday(d.year, d.month, 4, 3)


def is_triple_witching(d: date) -> bool:
    """Quarterly triple/quad witching — 3rd Friday of Mar/Jun/Sep/Dec."""
    return d.month in (3, 6, 9, 12) and is_third_friday(d)


def is_nfp_heuristic(d: date) -> bool:
    """Jobs report ≈ first Friday (a HEURISTIC, flagged — BLS occasionally shifts).

    Not authoritative; for trading, confirm against the BLS schedule. We expose it
    as a heuristic flag, never as a guaranteed date.
    """
    return d.weekday() == 4 and d == _nth_weekday(d.year, d.month, 4, 1)


def observed_holiday(d: date) -> str | None:
    """Name of the NYSE holiday on ``d`` (incl. weekend-observed shifts), else None."""
    md = (d.month, d.day)
    if md in _FIXED_HOLIDAYS and d.weekday() < 5:
        return _FIXED_HOLIDAYS[md]
    # Saturday holiday observed the preceding Friday; Sunday observed the next
    # Monday. Use real date arithmetic so month/year boundaries are handled —
    # naive day±1 integer math missed a Friday Dec 31 (New Year's, observed) and
    # a Monday in any month whose holiday fell on the 1st-of-month boundary.
    if d.weekday() == 4:
        nxt = d + timedelta(days=1)
        if (nxt.month, nxt.day) in _FIXED_HOLIDAYS:
            return _FIXED_HOLIDAYS[(nxt.month, nxt.day)] + " (observed)"
    if d.weekday() == 0:
        prev = d - timedelta(days=1)
        if (prev.month, prev.day) in _FIXED_HOLIDAYS:
            return _FIXED_HOLIDAYS[(prev.month, prev.day)] + " (observed)"
    return None


# --- Event risk (§6.3) -----------------------------------------------------
class EventRisk(NamedTuple):
    date: date
    events: list[str]  # deterministic + any scheduled events active today
    score: float  # [0,1] dispersion/uncertainty (NOT directional)
    label: str  # "quiet" | "elevated" | "high"


# Per-event dispersion weights (§6.3): FOMC/CPI dominate, OPEX is a vol/liquidity
# event. These gate *uncertainty*, not direction.
_EVENT_WEIGHT = {
    "FOMC": 1.0,
    "CPI": 0.9,
    "NFP": 0.7,
    "PCE": 0.55,
    "GDP": 0.5,
    "triple-witching": 0.5,
    "OPEX": 0.3,
}


def event_risk(d: date, scheduled_events: dict[date, list[str]] | None = None) -> EventRisk:
    """Dispersion/event-risk score for ``d``.

    ``scheduled_events`` maps a date to feed-required event names (FOMC, CPI, …)
    from a maintained schedule file — never inferred from a formula. Deterministic
    events (OPEX, triple-witching, NFP-heuristic, holidays) are computed here.
    """
    events: list[str] = []
    if observed_holiday(d):
        # Market closed — no intraday dispersion; report the holiday, score 0.
        return EventRisk(d, [f"holiday: {observed_holiday(d)}"], 0.0, "quiet")
    if is_triple_witching(d):
        events.append("triple-witching")
    elif is_third_friday(d):
        events.append("OPEX")
    if is_nfp_heuristic(d):
        events.append("NFP")
    for name in (scheduled_events or {}).get(d, []):
        if name not in events:
            events.append(name)

    # Combine weights with diminishing returns (two events aren't strictly additive).
    weights = sorted((_EVENT_WEIGHT.get(e, 0.4) for e in events), reverse=True)
    score = 0.0
    for i, w in enumerate(weights):
        score += w * (0.5**i)  # full first event, half the next, etc.
    score = min(1.0, score)
    label = "high" if score >= 0.8 else ("elevated" if score >= 0.4 else "quiet")
    return EventRisk(d, events, round(score, 3), label)


# --- Seasonality (§6.2) — shrunk hard --------------------------------------
class Seasonality(NamedTuple):
    date: date
    tilt: float  # small signed tilt in [-SEASONAL_CAP, +SEASONAL_CAP], + = bullish
    factors: list[str]  # which credible effects are active
    note: str

    @property
    def label(self) -> str:
        if self.tilt > 0.02:
            return "bullish tilt"
        if self.tilt < -0.02:
            return "bearish tilt"
        return "neutral"


# The seasonal tilt is intentionally tiny — a tilt, not a thesis (§6.2).
SEASONAL_CAP = 0.15


def _is_turn_of_month(d: date) -> bool:
    """TOM window: last trading day of month + first 3 of the next (approx by date).

    Approximation by calendar day (last 1 / first 3 business-ish days); the precise
    trading-day window can be layered when a market calendar is wired.
    """
    # first 3 business days of the month — weekday-gated so a Saturday/Sunday
    # near the 1st isn't mislabeled turn-of-month (it is not a trading day, and
    # _business_day_index returns -1 for a pre-business weekend date).
    if d.weekday() < 5 and d.day <= 5 and _business_day_index(d) < 3:
        return True
    # last business day of the month
    return _is_last_business_day(d)


def _business_day_index(d: date) -> int:
    """0-based count of weekdays from the 1st of the month through ``d``."""
    idx = -1
    for day in range(1, d.day + 1):
        if date(d.year, d.month, day).weekday() < 5:
            idx += 1
    return idx


def _is_last_business_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    nxt = d + timedelta(days=1)
    while nxt.month == d.month:
        if nxt.weekday() < 5:
            return False
        nxt += timedelta(days=1)
    return True


def _is_pre_holiday(d: date) -> bool:
    """The (business) day before an NYSE holiday."""
    nxt = d + timedelta(days=1)
    # skip weekend to the next market day
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return observed_holiday(nxt) is not None


def seasonality(d: date) -> Seasonality:
    """A small, honest seasonal tilt from the credible effects only (§6.2)."""
    tilt = 0.0
    factors: list[str] = []
    if _is_turn_of_month(d):
        tilt += 0.10  # primary: replicated + mechanism (Dash for Cash)
        factors.append("turn-of-month")
    if _is_pre_holiday(d):
        tilt += 0.04  # faint, decaying
        factors.append("pre-holiday")
    tilt = max(-SEASONAL_CAP, min(SEASONAL_CAP, tilt))
    note = (
        "small tilt from turn-of-month / pre-holiday only; day-of-week, Santa, "
        "September, Sell-in-May excluded (weak/overfit)"
    )
    return Seasonality(d, round(tilt, 3), factors, note)
