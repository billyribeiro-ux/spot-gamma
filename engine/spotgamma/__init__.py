"""spotgamma: an institutional-grade spot-gamma engine.

The engine calculates dealer gamma exposure from an options chain and reduces
it to actionable levels (zero gamma, call/put wall, volatility trigger). Data
sources are pluggable; ThinkScript and the dashboard only display the output.
"""

from .export_thinkscript import render_thinkscript
from .gex import aggregate_by_expiry, aggregate_by_strike, contract_gex, net_gex
from .levels import compute_levels
from .models import ChainSnapshot, GammaLevels, OptionContract, OptionType, StrikeGamma
from .profile import find_zero_gamma, gamma_profile
from .sources.base import ChainSource, get_source

__all__ = [
    "ChainSnapshot",
    "ChainSource",
    "GammaLevels",
    "OptionContract",
    "OptionType",
    "StrikeGamma",
    "aggregate_by_expiry",
    "aggregate_by_strike",
    "compute_levels",
    "contract_gex",
    "find_zero_gamma",
    "gamma_profile",
    "get_source",
    "net_gex",
    "render_thinkscript",
]

__version__ = "0.1.0"
