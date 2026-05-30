"""ThetaData chain source (via the local Theta Terminal gateway).

ThetaData serves OPRA-bundled real-time/historical options with greeks (incl.
**gamma**), IV, and open interest at retail prices. Requests go to the locally
running Theta Terminal REST gateway (default ``http://127.0.0.1:25510``), so no
API key travels in this adapter — the Terminal handles auth.

We use the bulk snapshot endpoints (one call returns every strike/expiration for
a root): ``/v2/bulk_snapshot/option/greeks`` and
``/v2/bulk_snapshot/option/open_interest``. Index SPX weeklies/0DTE live under
the ``SPXW`` root, so index symbols expand to multiple roots.

Response shape: ``{"header": {"format": [...col names...]}, "response": [
{"contract": {"root","expiration":YYYYMMDD,"strike":strike×1000,"right":"C"/"P"},
"ticks": [[...row...]]}, ...]}``.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

from ..models import ChainSnapshot, OptionContract, OptionType
from .base import ChainSource

_DEFAULT_BASE = "http://127.0.0.1:25510"

# Index symbols whose full chain spans an AM-settled root + a weekly/0DTE root.
_ROOTS: dict[str, list[str]] = {
    "SPX": ["SPX", "SPXW"],
    "NDX": ["NDX", "NDXP"],
    "RUT": ["RUT", "RUTW"],
}


def roots_for(symbol: str) -> list[str]:
    s = symbol.upper()
    return _ROOTS.get(s, [s])


def _row_lookup(payload: dict):
    """Return (format_index_map, response_list) for a bulk snapshot payload."""
    fmt = payload.get("header", {}).get("format", [])
    return {name: i for i, name in enumerate(fmt)}, payload.get("response", [])


def _contract_key(c: dict) -> tuple[int, int, str]:
    return (c["expiration"], c["strike"], c["right"])


def parse_theta_bulk(greeks_payload: dict, oi_payload: dict, symbol: str) -> ChainSnapshot:
    """Merge greeks + open-interest bulk snapshots into a ChainSnapshot (pure)."""
    oi_idx, oi_rows = _row_lookup(oi_payload)
    oi_by_contract: dict[tuple[int, int, str], int] = {}
    if "open_interest" in oi_idx:
        for item in oi_rows:
            ticks = item.get("ticks") or [[]]
            if ticks and ticks[0]:
                oi_by_contract[_contract_key(item["contract"])] = int(ticks[0][oi_idx["open_interest"]] or 0)

    g_idx, g_rows = _row_lookup(greeks_payload)
    contracts: list[OptionContract] = []
    spot = 0.0
    for item in g_rows:
        ticks = item.get("ticks") or []
        if not ticks or not ticks[0]:
            continue
        row = ticks[0]
        c = item["contract"]
        exp = c["expiration"]
        expiration = date(exp // 10000, (exp // 100) % 100, exp % 100)
        gamma = row[g_idx["gamma"]] if "gamma" in g_idx else None
        iv = row[g_idx["implied_vol"]] if "implied_vol" in g_idx else None
        if "underlying_price" in g_idx and row[g_idx["underlying_price"]]:
            spot = float(row[g_idx["underlying_price"]])
        contracts.append(
            OptionContract(
                option_type=OptionType.CALL if c["right"].upper() == "C" else OptionType.PUT,
                strike=c["strike"] / 1000.0,
                expiration=expiration,
                open_interest=oi_by_contract.get(_contract_key(c), 0),
                gamma=gamma if gamma else None,
                implied_volatility=iv if iv else None,
            )
        )
    if not spot:
        raise RuntimeError(f"ThetaData returned no underlying price for {symbol}")
    return ChainSnapshot(
        symbol=symbol.upper(),
        spot=spot,
        timestamp=datetime.now(timezone.utc),
        contracts=contracts,
    )


class ThetaDataSource(ChainSource):
    name = "thetadata"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.environ.get("THETADATA_URL", _DEFAULT_BASE)

    def _bulk(self, endpoint: str, root: str) -> dict:
        import requests

        resp = requests.get(
            f"{self.base_url}/v2/bulk_snapshot/option/{endpoint}",
            params={"root": root, "use_csv": "false"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def test_connection(self) -> tuple[bool, str]:
        import requests

        try:
            # Any HTTP response means the local Terminal gateway is up.
            r = requests.get(f"{self.base_url}/v2/system/mdds/status", timeout=8)
            return True, f"Theta Terminal reachable (HTTP {r.status_code})"
        except Exception as e:  # noqa: BLE001
            return False, f"Theta Terminal not reachable at {self.base_url}: {e}"

    def get_chain(self, symbol: str) -> ChainSnapshot:
        all_contracts: list[OptionContract] = []
        spot = 0.0
        for root in roots_for(symbol):
            snap = parse_theta_bulk(self._bulk("greeks", root), self._bulk("open_interest", root), symbol)
            all_contracts.extend(snap.contracts)
            spot = spot or snap.spot
        return ChainSnapshot(
            symbol=symbol.upper(),
            spot=spot,
            timestamp=datetime.now(timezone.utc),
            contracts=all_contracts,
        )
