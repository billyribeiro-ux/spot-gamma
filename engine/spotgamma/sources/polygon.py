"""Polygon.io (Massive) options chain-snapshot source.

Polygon's option-chain snapshot returns greeks (incl. **gamma**), IV, open
interest, and quotes per contract in one paginated call. Index options use the
``I:`` prefix (``I:SPX``, ``I:NDX``); the per-contract OCC ticker comes back as
``details.ticker`` (e.g. ``O:SPXW...``).

Auth: ``POLYGON_API_KEY``. Greeks/real-time require a paid Options plan; the
free/delayed tiers still return the chain structure.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from ..models import ChainSnapshot, OptionContract, OptionType
from .base import ChainSource

_BASE = "https://api.polygon.io"
_INDEX_SYMBOLS = {"SPX", "NDX", "RUT", "VIX", "XSP", "DJX"}


def polygon_underlying(symbol: str) -> str:
    s = symbol.upper()
    if s.startswith("I:"):
        return s
    return f"I:{s}" if s in _INDEX_SYMBOLS else s


def underlying_spot(results: list[dict]) -> float:
    """Extract the underlying level from a snapshot page.

    For index underlyings (``I:SPX``) Polygon returns the level under
    ``underlying_asset.value``; for equities/ETFs it's ``.price``. The object
    isn't guaranteed on every item, so scan until one carries a value.
    """
    for r in results:
        ua = r.get("underlying_asset") or {}
        level = ua.get("value") or ua.get("price")
        if level:
            return float(level)
    return 0.0


def parse_polygon_results(results: list[dict], symbol: str, spot: float) -> list[OptionContract]:
    """Normalize Polygon snapshot ``results`` into contracts (pure)."""
    out: list[OptionContract] = []
    for r in results:
        details = r.get("details", {})
        greeks = r.get("greeks", {})
        day = r.get("day", {})
        ctype = details.get("contract_type")
        out.append(
            OptionContract(
                option_type=OptionType.CALL if ctype == "call" else OptionType.PUT,
                strike=float(details["strike_price"]),
                expiration=datetime.strptime(details["expiration_date"], "%Y-%m-%d").date(),
                open_interest=int(r.get("open_interest") or 0),
                volume=int(day.get("volume") or 0),
                gamma=greeks.get("gamma"),
                implied_volatility=r.get("implied_volatility"),
            )
        )
    return out


class PolygonSource(ChainSource):
    name = "polygon"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("POLYGON_API_KEY")
        if not self.api_key:
            raise RuntimeError("PolygonSource requires POLYGON_API_KEY. Use --source cboe for a free option.")

    def test_connection(self) -> tuple[bool, str]:
        import requests

        try:
            r = requests.get(f"{_BASE}/v1/marketstatus/now", params={"apiKey": self.api_key}, timeout=15)
            if r.status_code in (401, 403):
                return False, f"{r.status_code} — API key rejected"
            r.raise_for_status()
            return True, "API key valid"
        except Exception as e:
            return False, str(e)

    def get_chain(self, symbol: str) -> ChainSnapshot:
        import requests

        underlying = polygon_underlying(symbol)
        url = f"{_BASE}/v3/snapshot/options/{underlying}"
        params = {"apiKey": self.api_key, "limit": 250}
        results: list[dict] = []
        spot = 0.0
        while url:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            page = body.get("results", [])
            results.extend(page)
            if not spot:
                spot = underlying_spot(page)
            # next_url already carries the cursor; only the apiKey must be re-added
            url = body.get("next_url")
            params = {"apiKey": self.api_key}
        if not spot:
            raise RuntimeError(f"Polygon returned no underlying price for {symbol}")
        return ChainSnapshot(
            symbol=symbol.upper().removeprefix("I:"),
            spot=spot,
            timestamp=datetime.now(UTC),
            contracts=parse_polygon_results(results, symbol, spot),
        )
