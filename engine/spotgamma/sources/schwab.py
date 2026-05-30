"""Charles Schwab Trader API chain source (ex–TD Ameritrade / thinkorswim).

Schwab's market-data chain returns greeks (delta, **gamma**, theta, vega, rho),
IV (``volatility``), and ``openInterest`` natively in one REST call — the most
"batteries-included" broker source. Free with an approved Schwab developer app
tied to a brokerage account.

Auth: OAuth2. This adapter expects a bearer access token in ``SCHWAB_ACCESS_TOKEN``
(obtain/refresh it out of band — Schwab refresh tokens last 7 days). Index
symbols use the ``$SPX`` / ``$NDX`` convention.

Response shape: ``callExpDateMap`` / ``putExpDateMap`` are nested dicts
``{"YYYY-MM-DD:DTE": {"<strike>": [contractObj, ...]}}``.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from ..models import ChainSnapshot, OptionContract, OptionType
from .base import ChainSource

_BASE = "https://api.schwabapi.com/marketdata/v1"
_INDEX_SYMBOLS = {"SPX", "NDX", "RUT", "VIX", "XSP", "DJX"}


def schwab_symbol(symbol: str) -> str:
    s = symbol.upper().lstrip("$")
    return f"${s}" if s in _INDEX_SYMBOLS else s


def _emit(exp_map: dict, opt_type: OptionType, out: list[OptionContract]) -> None:
    for _exp_key, strikes in exp_map.items():
        for _strike, contracts in strikes.items():
            for c in contracts:
                exp_ms = c.get("expirationDate")
                expiration = (
                    datetime.fromtimestamp(exp_ms / 1000, tz=timezone.utc).date()
                    if exp_ms
                    else datetime.strptime(c["expirationDate"][:10], "%Y-%m-%d").date()
                )
                gamma = c.get("gamma")
                # Schwab sends -999.0 for greeks it could not compute.
                gamma = None if gamma in (None, -999.0) else gamma
                out.append(
                    OptionContract(
                        option_type=opt_type,
                        strike=float(c["strikePrice"]),
                        expiration=expiration,
                        open_interest=int(c.get("openInterest") or 0),
                        volume=int(c.get("totalVolume") or 0),
                        gamma=gamma,
                        implied_volatility=(c.get("volatility") / 100.0 if c.get("volatility") not in (None, -999.0) else None),
                        bid=c.get("bid"),
                        ask=c.get("ask"),
                    )
                )


def parse_schwab_chain(payload: dict, symbol: str) -> ChainSnapshot:
    """Normalize a Schwab /chains payload into a ChainSnapshot (pure)."""
    contracts: list[OptionContract] = []
    _emit(payload.get("callExpDateMap", {}), OptionType.CALL, contracts)
    _emit(payload.get("putExpDateMap", {}), OptionType.PUT, contracts)
    spot = float(payload.get("underlyingPrice") or payload.get("underlying", {}).get("last"))
    return ChainSnapshot(
        symbol=symbol.upper().lstrip("$"),
        spot=spot,
        timestamp=datetime.now(timezone.utc),
        contracts=contracts,
    )


class SchwabSource(ChainSource):
    name = "schwab"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("SCHWAB_ACCESS_TOKEN")
        if not self.token:
            raise RuntimeError(
                "SchwabSource requires SCHWAB_ACCESS_TOKEN (OAuth2 bearer token). "
                "Use --source cboe for a free no-auth option."
            )

    def test_connection(self) -> tuple[bool, str]:
        import requests

        try:
            r = requests.get(
                f"{_BASE}/quotes",
                params={"symbols": "SPY"},
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                timeout=15,
            )
            if r.status_code == 401:
                return False, "401 — token expired or invalid (Schwab tokens refresh every 7 days)"
            r.raise_for_status()
            return True, "Authenticated; market data reachable"
        except Exception as e:  # noqa: BLE001
            return False, str(e)

    def get_chain(self, symbol: str) -> ChainSnapshot:
        import requests

        resp = requests.get(
            f"{_BASE}/chains",
            params={"symbol": schwab_symbol(symbol), "includeUnderlyingQuote": "true"},
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return parse_schwab_chain(resp.json(), symbol)
