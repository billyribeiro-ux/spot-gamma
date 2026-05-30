"""tastytrade chain source (REST chain + DXLink/dxFeed streaming greeks).

Unlike Schwab/Tradier, tastytrade's REST option-chain returns only contract
metadata (strikes, expirations, and a dxFeed ``streamer-symbol``). Greeks
(**gamma**, IV) and open interest arrive over a **DXLink websocket**, so this
adapter:

  1. logs in (session token) and pulls an api-quote-token,
  2. fetches the nested chain to map streamer-symbol -> (expiry, strike, type),
  3. reads underlying spot from REST /market-data/by-type (indices don't emit
     DXLink Trade events, so they can't be priced off the stream),
  4. opens DXLink, subscribes Greeks + Summary, collects a snapshot until
     coverage is reached or a timeout elapses.

Auth via ``TASTYTRADE_USERNAME`` / ``TASTYTRADE_PASSWORD`` (or pass a session
token). Requires the ``stream`` extra (``websockets``). Free with a funded
account. **Experimental** — the REST/pure parsing is unit-tested; the live
streaming path needs verification against a real account.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import ClassVar, NamedTuple

from ..models import ChainSnapshot, OptionContract, OptionType
from ._normalize import normalize_iv
from .base import ChainSource

_PROD = "https://api.tastytrade.com"
_INDEX_SYMBOLS = {"SPX", "NDX", "RUT", "VIX", "XSP", "DJX"}


class ChainMeta(NamedTuple):
    streamer_symbol: str
    expiration: str  # ISO date
    strike: float
    option_type: OptionType


def parse_nested_chain(payload: dict) -> list[ChainMeta]:
    """Map a /option-chains/{sym}/nested response to ChainMeta rows (pure)."""
    out: list[ChainMeta] = []
    for item in payload.get("data", {}).get("items", []):
        for exp in item.get("expirations", []):
            exp_date = exp["expiration-date"]
            for s in exp.get("strikes", []):
                strike = float(s["strike-price"])
                out.append(ChainMeta(s["call-streamer-symbol"], exp_date, strike, OptionType.CALL))
                out.append(ChainMeta(s["put-streamer-symbol"], exp_date, strike, OptionType.PUT))
    return out


def build_snapshot(
    chain: list[ChainMeta],
    greeks_by_sym: dict[str, dict],
    oi_by_sym: dict[str, int],
    spot: float,
    symbol: str,
) -> ChainSnapshot:
    """Combine chain metadata with streamed greeks/OI into a snapshot (pure)."""
    contracts: list[OptionContract] = []
    for meta in chain:
        g = greeks_by_sym.get(meta.streamer_symbol, {})
        contracts.append(
            OptionContract(
                option_type=meta.option_type,
                strike=meta.strike,
                expiration=datetime.strptime(meta.expiration, "%Y-%m-%d").date(),
                open_interest=int(oi_by_sym.get(meta.streamer_symbol, 0)),
                gamma=g.get("gamma"),
                implied_volatility=normalize_iv(g.get("volatility")),
            )
        )
    return ChainSnapshot(symbol=symbol.upper(), spot=spot, timestamp=datetime.now(UTC), contracts=contracts)


def parse_compact_feed(data: list, field_counts: dict[str, int]) -> list[tuple[str, list]]:
    """Decode a DXLink COMPACT FEED_DATA payload.

    ``data`` is ``[eventType, flatArray]``; the flat array repeats one record's
    fields back-to-back. Returns ``(eventType, fields)`` per record.
    """
    out: list[tuple[str, list]] = []
    i = 0
    while i + 1 < len(data):
        etype = data[i]
        flat = data[i + 1]
        n = field_counts.get(etype)
        if not n:
            break
        for j in range(0, len(flat), n):
            out.append((etype, flat[j : j + n]))
        i += 2
    return out


class TastytradeSource(ChainSource):
    name = "tastytrade"

    # Greeks: [eventType, eventSymbol, gamma, volatility]; Summary: [..., openInterest]
    _GREEKS_FIELDS: ClassVar[list[str]] = ["eventType", "eventSymbol", "gamma", "volatility"]
    _SUMMARY_FIELDS: ClassVar[list[str]] = ["eventType", "eventSymbol", "openInterest"]

    def __init__(self, username: str | None = None, password: str | None = None, base_url: str = _PROD) -> None:
        self.username = username or os.environ.get("TASTYTRADE_USERNAME")
        self.password = password or os.environ.get("TASTYTRADE_PASSWORD")
        self.base_url = base_url
        if not (self.username and self.password):
            raise RuntimeError(
                "TastytradeSource requires TASTYTRADE_USERNAME/PASSWORD. Use --source cboe for a free no-auth option."
            )

    # --- REST -------------------------------------------------------------
    # `http` is the shared retrying session; `session` is the tastytrade auth token.
    def _session_token(self, http) -> str:
        r = http.post(
            f"{self.base_url}/sessions",
            json={"login": self.username, "password": self.password},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["data"]["session-token"]

    def _quote_token(self, http, session: str) -> tuple[str, str]:
        r = http.get(
            f"{self.base_url}/api-quote-tokens",
            headers={"Authorization": session},
            timeout=20,
        )
        r.raise_for_status()
        d = r.json()["data"]
        return d["token"], d["dxlink-url"]

    def _nested_chain(self, http, session: str, symbol: str) -> list[ChainMeta]:
        r = http.get(
            f"{self.base_url}/option-chains/{symbol.upper()}/nested",
            headers={"Authorization": session},
            timeout=30,
        )
        r.raise_for_status()
        return parse_nested_chain(r.json())

    def _market_spot(self, http, session: str, symbol: str) -> float:
        """Underlying level via REST. Indices don't emit DXLink Trade events, so
        the streaming path can't price them — /market-data/by-type can."""
        s = symbol.upper()
        bucket = "indices" if s in _INDEX_SYMBOLS else "equities"
        r = http.get(
            f"{self.base_url}/market-data/by-type",
            params={bucket: s},
            headers={"Authorization": session},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("data", {}).get("items", [])
        if not items:
            return 0.0
        q = items[0]
        return float(q.get("last") or q.get("mark") or q.get("close") or 0.0)

    def test_connection(self) -> tuple[bool, str]:
        from ._http import session as http_factory

        try:
            http = http_factory()
            session = self._session_token(http)
            # validate we can also mint a quote token (needed for streaming greeks)
            self._quote_token(http, session)
            return True, "Logged in; streaming quote token issued"
        except Exception as e:
            return False, str(e)

    # --- Streaming --------------------------------------------------------
    def _collect(self, dxlink_url: str, token: str, chain: list[ChainMeta], timeout: float):
        import asyncio

        return asyncio.run(self._collect_async(dxlink_url, token, chain, timeout))

    async def _collect_async(self, dxlink_url, token, chain, timeout):
        import asyncio
        import json

        import websockets

        field_counts = {"Greeks": 4, "Summary": 3}
        greeks: dict[str, dict] = {}
        oi: dict[str, int] = {}
        symbols = [m.streamer_symbol for m in chain]

        async with websockets.connect(dxlink_url, max_size=None) as ws:

            async def send(msg):
                await ws.send(json.dumps(msg))

            await send(
                {
                    "type": "SETUP",
                    "channel": 0,
                    "version": "0.1-spotgamma",
                    "keepaliveTimeout": 60,
                    "acceptKeepaliveTimeout": 60,
                }
            )
            await send({"type": "AUTH", "channel": 0, "token": token})
            await send({"type": "CHANNEL_REQUEST", "channel": 1, "service": "FEED", "parameters": {"contract": "AUTO"}})
            await send(
                {
                    "type": "FEED_SETUP",
                    "channel": 1,
                    "acceptAggregationPeriod": 0.1,
                    "acceptDataFormat": "COMPACT",
                    "acceptEventFields": {"Greeks": self._GREEKS_FIELDS, "Summary": self._SUMMARY_FIELDS},
                }
            )
            sub = [{"type": "Greeks", "symbol": s} for s in symbols]
            sub += [{"type": "Summary", "symbol": s} for s in symbols]
            # DXLink rejects oversized subscription messages (WS 1009); chunk it.
            for k in range(0, len(sub), 500):
                await send({"type": "FEED_SUBSCRIPTION", "channel": 1, "add": sub[k : k + 500]})

            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=deadline - asyncio.get_event_loop().time())
                except TimeoutError:
                    break
                msg = json.loads(raw)
                if msg.get("type") == "KEEPALIVE":
                    await send({"type": "KEEPALIVE", "channel": 0})
                    continue
                if msg.get("type") != "FEED_DATA":  # ignores AUTH_STATE/CHANNEL_OPENED/FEED_CONFIG
                    continue
                for etype, fields in parse_compact_feed(msg["data"], field_counts):
                    if etype == "Greeks":
                        _, sym, gamma, vol = fields
                        greeks[sym] = {"gamma": gamma, "volatility": vol}
                    elif etype == "Summary":
                        _, sym, oi_val = fields
                        oi[sym] = oi_val or 0
                if len(greeks) >= len(symbols):
                    break
        return greeks, oi

    # --- ChainSource ------------------------------------------------------
    def get_chain(self, symbol: str, timeout: float = 20.0) -> ChainSnapshot:
        from ._http import session as http_factory

        http = http_factory()
        session = self._session_token(http)
        token, dxlink_url = self._quote_token(http, session)
        chain = self._nested_chain(http, session, symbol)
        spot = self._market_spot(http, session, symbol)
        if not spot:
            raise RuntimeError(f"tastytrade returned no underlying price for {symbol}")
        greeks, oi = self._collect(dxlink_url, token, chain, timeout)
        return build_snapshot(chain, greeks, oi, spot, symbol)
