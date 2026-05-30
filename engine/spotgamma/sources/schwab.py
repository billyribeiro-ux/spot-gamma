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
from datetime import UTC, datetime

from ..models import ChainSnapshot, OptionContract, OptionType
from ._normalize import normalize_iv
from .base import ChainSource

_BASE = "https://api.schwabapi.com/marketdata/v1"
_INDEX_SYMBOLS = {"SPX", "NDX", "RUT", "VIX", "XSP", "DJX"}


def schwab_symbol(symbol: str) -> str:
    s = symbol.upper().lstrip("$")
    return f"${s}" if s in _INDEX_SYMBOLS else s


def _clean(value) -> float | None:
    """Drop Schwab's ``-999`` (and NaN) sentinels for uncomputed greeks/IV."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None  # guards stray "NaN" strings the API can emit
    return None if (v != v or v <= -999.0) else v


def _emit(exp_map: dict, opt_type: OptionType, out: list[OptionContract]) -> None:
    for exp_key, strikes in exp_map.items():
        # The map key is the authoritative calendar date ("YYYY-MM-DD:DTE");
        # use it instead of the epoch-ms field to avoid UTC off-by-one drift.
        expiration = datetime.strptime(exp_key.split(":")[0], "%Y-%m-%d").date()
        for _strike, contracts in strikes.items():
            for c in contracts:
                out.append(
                    OptionContract(
                        option_type=opt_type,
                        strike=float(c["strikePrice"]),
                        expiration=expiration,
                        open_interest=int(c.get("openInterest") or 0),
                        volume=int(c.get("totalVolume") or 0),
                        gamma=_clean(c.get("gamma")),
                        # Schwab IV is percent points; normalize_iv handles the /100
                        # and drops the -999 sentinel.
                        implied_volatility=normalize_iv(c.get("volatility")),
                        bid=c.get("bid"),
                        ask=c.get("ask"),
                    )
                )


def parse_schwab_chain(payload: dict, symbol: str) -> ChainSnapshot:
    """Normalize a Schwab /chains payload into a ChainSnapshot (pure)."""
    contracts: list[OptionContract] = []
    _emit(payload.get("callExpDateMap", {}), OptionType.CALL, contracts)
    _emit(payload.get("putExpDateMap", {}), OptionType.PUT, contracts)
    raw_spot = payload.get("underlyingPrice") or payload.get("underlying", {}).get("last")
    if raw_spot is None:
        raise RuntimeError(f"Schwab returned no underlying price for {symbol}")
    spot = float(raw_spot)
    return ChainSnapshot(
        symbol=symbol.upper().lstrip("$"),
        spot=spot,
        timestamp=datetime.now(UTC),
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
        from ._http import session

        try:
            r = session().get(
                f"{_BASE}/quotes",
                params={"symbols": "SPY"},
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                timeout=15,
            )
            if r.status_code == 401:
                return False, "401 — token expired or invalid (Schwab tokens refresh every 7 days)"
            r.raise_for_status()
            return True, "Authenticated; market data reachable"
        except Exception as e:
            return False, str(e)

    def get_chain(self, symbol: str) -> ChainSnapshot:
        from ._http import session

        resp = session().get(
            f"{_BASE}/chains",
            params={"symbol": schwab_symbol(symbol), "includeUnderlyingQuote": "true"},
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return parse_schwab_chain(resp.json(), symbol)
