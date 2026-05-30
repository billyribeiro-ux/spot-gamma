"""Cboe delayed-quotes chain source — FREE, no account, no API key.

Cboe publishes a public delayed (~15-min) JSON chain on its CDN that already
includes greeks (gamma), IV, and open interest for the whole chain, including
the SPXW weekly/0DTE root. This is the zero-cost way to run the engine on real
index data.

Endpoint (verified): ``https://cdn.cboe.com/api/global/delayed_quotes/options/{key}.json``
where index symbols take a leading underscore (``_SPX``, ``_NDX``) and ETFs do
not (``SPY``, ``QQQ``).

Caveats: unofficial/undocumented endpoint, ~15-min delayed, and Cboe's ToS
restricts automated scraping — fine for personal research, not redistribution.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import ChainSnapshot, OptionContract
from .base import ChainSource
from .occ import parse_occ_symbol

_BASE = "https://cdn.cboe.com/api/global/delayed_quotes/options"
# Cash-settled index roots need the underscore-prefixed CDN key.
_INDEX_SYMBOLS = {"SPX", "NDX", "RUT", "VIX", "XSP", "DJX"}


def cdn_key(symbol: str) -> str:
    s = symbol.upper().lstrip("_")
    return f"_{s}" if s in _INDEX_SYMBOLS else s


def parse_cboe_payload(payload: dict, symbol: str) -> ChainSnapshot:
    """Normalize a Cboe delayed-quotes payload into a ChainSnapshot.

    Pure function (no network) so it can be unit-tested against a fixture.
    """
    data = payload["data"]
    spot = float(data["current_price"])
    ts_raw = payload.get("timestamp")
    try:
        timestamp = datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc) if ts_raw else datetime.now(timezone.utc)
    except ValueError:
        timestamp = datetime.now(timezone.utc)

    contracts: list[OptionContract] = []
    for o in data["options"]:
        _root, expiration, opt_type, strike = parse_occ_symbol(o["option"])
        contracts.append(
            OptionContract(
                option_type=opt_type,
                strike=strike,
                expiration=expiration,
                open_interest=int(o.get("open_interest") or 0),
                volume=int(o.get("volume") or 0),
                gamma=o.get("gamma"),
                implied_volatility=o.get("iv"),
                bid=o.get("bid"),
                ask=o.get("ask"),
            )
        )
    return ChainSnapshot(
        symbol=symbol.upper().lstrip("_"),
        spot=spot,
        timestamp=timestamp,
        contracts=contracts,
    )


class CboeSource(ChainSource):
    name = "cboe"

    def get_chain(self, symbol: str) -> ChainSnapshot:
        import requests  # local import: only needed when this adapter is used

        url = f"{_BASE}/{cdn_key(symbol)}.json"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return parse_cboe_payload(resp.json(), symbol)

    def test_connection(self) -> tuple[bool, str]:
        import requests

        # stream + immediate close fetches headers only (the JSON is multi-MB).
        resp = requests.get(f"{_BASE}/{cdn_key('SPY')}.json", stream=True, timeout=15)
        ok = resp.ok
        status = resp.status_code
        resp.close()
        return ok, ("Cboe CDN reachable" if ok else f"HTTP {status}")
