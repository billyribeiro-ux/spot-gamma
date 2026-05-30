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

    def test_connection(self) -> tuple[bool, str]:
        """Cheap reachability/auth check for the admin hub.

        Returns ``(ok, message)``. The default succeeds for sources that need no
        network (e.g. sample); networked adapters override with a light probe.
        """
        return True, "ready"


# Registered sources. Lazy importers keep an unused adapter's optional deps
# (requests, websockets) from blocking startup.
def _load(module: str, cls: str):
    def factory() -> ChainSource:
        import importlib

        return getattr(importlib.import_module(f".{module}", __package__), cls)()

    return factory


_SOURCES = {
    "sample": _load("sample", "SampleSource"),
    "cboe": _load("cboe", "CboeSource"),
    "tradier": _load("tradier", "TradierSource"),
    "schwab": _load("schwab", "SchwabSource"),
    "polygon": _load("polygon", "PolygonSource"),
    "thetadata": _load("thetadata", "ThetaDataSource"),
    "tastytrade": _load("tastytrade", "TastytradeSource"),
}

SOURCE_NAMES = sorted(_SOURCES)


def get_source(name: str) -> ChainSource:
    """Factory: resolve a chain source by name."""
    try:
        return _SOURCES[name.lower()]()
    except KeyError:
        raise ValueError(f"unknown source: {name!r} (known: {', '.join(SOURCE_NAMES)})") from None
