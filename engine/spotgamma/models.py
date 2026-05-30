"""Core data models for the spot-gamma engine.

These pydantic models are the contract between data sources, the gamma
calculation engine, and any consumer (CLI, API, dashboard). Keeping them
strict and well-typed means a chain from any vendor adapter normalizes to the
same shape before any gamma math runs.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

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


class OptionType(str, Enum):
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
    gamma: Optional[float] = Field(default=None, ge=0)
    implied_volatility: Optional[float] = Field(default=None, ge=0)
    bid: Optional[float] = None
    ask: Optional[float] = None

    @property
    def mark(self) -> Optional[float]:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0
        return None


class ChainSnapshot(BaseModel):
    """A full option chain for one underlying at one point in time."""

    symbol: str
    spot: float = Field(gt=0)
    timestamp: datetime
    risk_free_rate: float = 0.04
    contracts: list[OptionContract]

    @property
    def multiplier(self) -> int:
        return CONTRACT_MULTIPLIER.get(self.symbol.upper(), DEFAULT_MULTIPLIER)

    def dte(self, expiration: date) -> float:
        """Calendar days to expiration as a fraction of a year (ACT/365)."""
        days = (expiration - self.timestamp.date()).days
        return max(days, 0) / 365.0


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
    zero_gamma: Optional[float]
    volatility_trigger: Optional[float]
    call_wall: Optional[float]
    put_wall: Optional[float]
    absolute_gamma: Optional[float] = None  # strike with the most total gamma
    hedge_wall: Optional[float] = None      # strike with the largest net dealer gamma

    top_positive_nodes: list[StrikeGamma]
    top_negative_nodes: list[StrikeGamma]
    by_strike: list[StrikeGamma]
    by_expiry: list[ExpiryGamma]
    zero_dte_net_gex: float
    zero_dte_share: float  # fraction of total |gamma| sitting in 0DTE
