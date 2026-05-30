"""Tradier live chain source (Greeks + open interest via ORATS).

Recommended first live adapter: Tradier's options/chains endpoint returns
``greeks.gamma``, ``greeks.mid_iv`` and ``open_interest`` per contract when
``greeks=true``, so no local Black-Scholes is needed for the snapshot.

Auth: set ``TRADIER_TOKEN`` (and optionally ``TRADIER_BASE_URL`` to switch
between sandbox and production). This adapter is intentionally not exercised by
the offline test suite; it is the upgrade path from the sample source.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from ..models import ChainSnapshot, OptionContract, OptionType
from .base import ChainSource

_PROD = "https://api.tradier.com/v1"


class TradierSource(ChainSource):
    name = "tradier"

    def __init__(self, token: str | None = None, base_url: str | None = None) -> None:
        self.token = token or os.environ.get("TRADIER_TOKEN")
        self.base_url = base_url or os.environ.get("TRADIER_BASE_URL", _PROD)
        if not self.token:
            raise RuntimeError(
                "TradierSource requires a token: set TRADIER_TOKEN or pass token=. "
                "Use --source sample for offline runs."
            )

    # --- HTTP helpers -----------------------------------------------------
    def _get(self, path: str, params: dict):
        import requests  # local import: only needed when this adapter is used

        resp = requests.get(
            f"{self.base_url}{path}",
            params=params,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _quote_spot(self, symbol: str) -> float:
        data = self._get("/markets/quotes", {"symbols": symbol})
        q = data["quotes"]["quote"]
        q = q[0] if isinstance(q, list) else q
        return float(q["last"])

    def _expirations(self, symbol: str) -> list[str]:
        data = self._get("/markets/options/expirations", {"symbol": symbol})
        dates = (data.get("expirations") or {}).get("date") or []
        return dates if isinstance(dates, list) else [dates]

    def test_connection(self) -> tuple[bool, str]:
        try:
            self._get("/markets/quotes", {"symbols": "SPY"})
            return True, "Authenticated; market data reachable"
        except Exception as e:  # noqa: BLE001 — surface any auth/network failure
            return False, str(e)

    # --- ChainSource ------------------------------------------------------
    def get_chain(self, symbol: str) -> ChainSnapshot:
        spot = self._quote_spot(symbol)
        contracts: list[OptionContract] = []
        for exp in self._expirations(symbol):
            data = self._get("/markets/options/chains", {"symbol": symbol, "expiration": exp, "greeks": "true"})
            options = (data.get("options") or {}).get("option") or []
            if isinstance(options, dict):
                options = [options]
            for o in options:
                greeks = o.get("greeks") or {}
                contracts.append(
                    OptionContract(
                        option_type=OptionType.CALL if o["option_type"] == "call" else OptionType.PUT,
                        strike=float(o["strike"]),
                        expiration=datetime.strptime(exp, "%Y-%m-%d").date(),
                        open_interest=int(o.get("open_interest") or 0),
                        volume=int(o.get("volume") or 0),
                        gamma=greeks.get("gamma"),
                        implied_volatility=greeks.get("mid_iv"),
                        bid=o.get("bid"),
                        ask=o.get("ask"),
                    )
                )
        return ChainSnapshot(
            symbol=symbol.upper(),
            spot=spot,
            timestamp=datetime.now(timezone.utc),
            contracts=contracts,
        )
