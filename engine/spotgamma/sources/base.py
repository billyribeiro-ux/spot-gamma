"""Vendor-neutral chain source interface.

Any data provider (sample fixtures, Tradier, ORATS, Databento, ...) implements
this single method. The engine never imports a vendor SDK directly — it only
ever sees a normalized :class:`ChainSnapshot`. This is what lets us swap or add
data sources without touching gamma math, the API, or the dashboard.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ChainSnapshot


class ChainSource(ABC):
    name: str = "base"

    @abstractmethod
    def get_chain(self, symbol: str) -> ChainSnapshot:
        """Return a normalized chain snapshot for ``symbol`` (e.g. "SPX")."""
        raise NotImplementedError


def get_source(name: str) -> ChainSource:
    """Factory: resolve a source by name. Imports are local so an unused
    adapter's optional dependencies (e.g. ``requests``) never block startup."""
    key = name.lower()
    if key == "sample":
        from .sample import SampleSource

        return SampleSource()
    if key == "tradier":
        from .tradier import TradierSource

        return TradierSource()
    raise ValueError(f"unknown source: {name!r} (known: sample, tradier)")
