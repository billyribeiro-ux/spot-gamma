"""Core data models for the spot-gamma engine.

These pydantic models are the contract between data sources, the gamma
calculation engine, and any consumer (CLI, API, dashboard). Keeping them
strict and well-typed means a chain from any vendor adapter normalizes to the
same shape before any gamma math runs.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

# US options expire on the US/Eastern trading calendar; anchoring DTE and 0DTE
# to ET (not UTC) avoids an off-by-one when a snapshot is taken after ~20:00 ET,
# when the UTC date has already rolled to "tomorrow".
_MARKET_TZ = ZoneInfo("America/New_York")

# Index/ETF options in scope all use the standard 100x multiplier. Kept as a
# mapping (rather than a constant) so single-name or futures options with other
# multipliers can be added later without touching call sites.
CONTRACT_MULTIPLIER: dict[str, int] = {
    "SPX": 100,
    "NDX": 100,
    "SPY": 100,
    "QQQ": 100,
}
DEFAULT_MULTIPLIER = 100


class OptionType(StrEnum):
    CALL = "call"
    PUT = "put"


class OptionContract(BaseModel):
    """A single option line from a chain snapshot.

    `gamma` is the per-share Black-Scholes gamma as supplied by the data
    source. It may be ``None`` when a source provides IV but not greeks; in
    that case the engine fills it via :mod:`spotgamma.greeks`.
    """

    option_type: OptionType
    strike: float = Field(gt=0)
    expiration: date
    open_interest: int = Field(ge=0)
    volume: int = Field(default=0, ge=0)
    gamma: float | None = Field(default=None, ge=0)
    implied_volatility: float | None = Field(default=None, ge=0)
    bid: float | None = None
    ask: float | None = None

    @property
    def mark(self) -> float | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0
        return None


class ChainSnapshot(BaseModel):
    """A full option chain for one underlying at one point in time."""

    symbol: str
    spot: float = Field(gt=0)
    timestamp: datetime
    risk_free_rate: float = 0.04
    dividend_yield: float = 0.0  # continuous; carry term in the BS gamma fallback/profile
    contracts: list[OptionContract]

    @property
    def multiplier(self) -> int:
        return CONTRACT_MULTIPLIER.get(self.symbol.upper(), DEFAULT_MULTIPLIER)

    @property
    def session_date(self) -> date:
        """The snapshot's trading-session date in US/Eastern (see _MARKET_TZ).

        Naive timestamps are assumed to already be UTC.
        """
        ts = self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(tzinfo=ZoneInfo("UTC"))
        return ts.astimezone(_MARKET_TZ).date()

    def days_to_expiry(self, expiration: date) -> int:
        """Whole calendar days to expiration on the ET trading calendar (>= 0)."""
        return max((expiration - self.session_date).days, 0)

    def dte(self, expiration: date) -> float:
        """Time to expiration as a fraction of a year (ACT/365)."""
        return self.days_to_expiry(expiration) / 365.0


class StrikeGamma(BaseModel):
    """Aggregated dollar gamma exposure at a single strike."""

    strike: float
    call_gex: float
    put_gex: float

    @property
    def net_gex(self) -> float:
        return self.call_gex + self.put_gex

    @property
    def total_abs_gex(self) -> float:
        return abs(self.call_gex) + abs(self.put_gex)


class ExpiryGamma(BaseModel):
    """Aggregated net dollar gamma exposure for a single expiration."""

    expiration: date
    net_gex: float
    dte_days: int


class GammaLevels(BaseModel):
    """The finished, dealer-facing output of the engine.

    This is what the API serves and the dashboard / ThinkScript consume.
    """

    symbol: str
    spot: float
    timestamp: datetime

    net_gex: float
    regime: str  # "positive" | "negative"
    zero_gamma: float | None
    volatility_trigger: float | None
    call_wall: float | None
    put_wall: float | None
    absolute_gamma: float | None = None  # strike with the most total gamma
    hedge_wall: float | None = None  # strike with the largest net dealer gamma

    top_positive_nodes: list[StrikeGamma]
    top_negative_nodes: list[StrikeGamma]
    by_strike: list[StrikeGamma]
    by_expiry: list[ExpiryGamma]
    zero_dte_net_gex: float
    zero_dte_share: float  # fraction of total |gamma| sitting in 0DTE
