"""Pure normalization tests for the live adapters (no network).

Each adapter factors its provider-specific JSON into a pure parser; we feed a
small synthetic payload shaped like the real response and assert it normalizes
to a ChainSnapshot the engine can consume.
"""

from datetime import date

import pytest
from spotgamma.levels import compute_levels
from spotgamma.models import OptionType
from spotgamma.sources.base import SOURCE_NAMES, get_source
from spotgamma.sources.cboe import cdn_key, parse_cboe_payload
from spotgamma.sources.occ import parse_occ_symbol
from spotgamma.sources.polygon import parse_polygon_results, polygon_underlying, underlying_spot
from spotgamma.sources.schwab import parse_schwab_chain, schwab_symbol
from spotgamma.sources.specs import SOURCE_SPECS, build_source
from spotgamma.sources.tastytrade import build_snapshot, parse_compact_feed, parse_nested_chain
from spotgamma.sources.thetadata import parse_theta_bulk, roots_for


def test_registry_lists_all_adapters():
    assert set(SOURCE_NAMES) == {"sample", "cboe", "tradier", "schwab", "polygon", "thetadata", "tastytrade"}
    with pytest.raises(ValueError):
        get_source("nope")


def test_specs_cover_every_source_and_build():
    # every registered source has a connection spec
    assert set(SOURCE_SPECS) == set(SOURCE_NAMES)
    # credential-free sources build and report a connection spec correctly
    assert SOURCE_SPECS["cboe"].needs_credentials is False
    assert SOURCE_SPECS["polygon"].fields[0].key == "api_key"
    sample = build_source("sample")
    assert sample.test_connection()[0] is True  # default probe succeeds offline
    # credentialed sources raise cleanly when neither creds nor env are present
    with pytest.raises(RuntimeError):
        build_source("schwab", {})
    with pytest.raises(ValueError):
        build_source("bogus")


def test_parse_occ_symbol():
    root, exp, opt, strike = parse_occ_symbol("SPXW260618C00200000")
    assert root == "SPXW" and exp == date(2026, 6, 18)
    assert opt is OptionType.CALL and strike == 200.0
    # vendor prefix + put
    _, _, opt2, strike2 = parse_occ_symbol("O:SPX260320P05850000")
    assert opt2 is OptionType.PUT and strike2 == 5850.0


def test_cboe_symbol_mapping_and_parse():
    assert cdn_key("SPX") == "_SPX" and cdn_key("NDX") == "_NDX"
    assert cdn_key("SPY") == "SPY" and cdn_key("_SPX") == "_SPX"
    payload = {
        "timestamp": "2026-05-29 15:00:00",
        "data": {
            "current_price": 5850.0,
            "options": [
                {
                    "option": "SPX260618C05900000",
                    "gamma": 0.001,
                    "iv": 0.16,
                    "open_interest": 1000,
                    "volume": 5,
                    "bid": 1,
                    "ask": 2,
                },
                {"option": "SPX260618P05800000", "gamma": 0.001, "iv": 0.17, "open_interest": 2000, "volume": 7},
            ],
        },
    }
    snap = parse_cboe_payload(payload, "SPX")
    assert snap.symbol == "SPX" and snap.spot == 5850.0 and len(snap.contracts) == 2
    call = next(c for c in snap.contracts if c.option_type is OptionType.CALL)
    assert call.strike == 5900.0 and call.gamma == 0.001 and call.open_interest == 1000
    compute_levels(snap)  # must flow through the engine


def test_schwab_symbol_mapping_and_parse():
    assert schwab_symbol("SPX") == "$SPX" and schwab_symbol("QQQ") == "QQQ"
    payload = {
        "underlyingPrice": 5850.0,
        "callExpDateMap": {
            "2026-06-18:20": {
                "5900.0": [
                    {
                        "strikePrice": 5900,
                        "expirationDate": 1781827200000,
                        "gamma": 0.001,
                        "volatility": 16.0,
                        "openInterest": 1000,
                        "totalVolume": 5,
                    }
                ]
            }
        },
        "putExpDateMap": {
            "2026-06-18:20": {
                "5800.0": [
                    {
                        "strikePrice": 5800,
                        "expirationDate": 1781827200000,
                        "gamma": -999.0,
                        "volatility": -999.0,
                        "openInterest": 2000,
                        "totalVolume": 7,
                    }
                ]
            }
        },
    }
    snap = parse_schwab_chain(payload, "SPX")
    assert snap.spot == 5850.0 and len(snap.contracts) == 2
    call = next(c for c in snap.contracts if c.option_type is OptionType.CALL)
    put = next(c for c in snap.contracts if c.option_type is OptionType.PUT)
    assert call.gamma == 0.001 and abs(call.implied_volatility - 0.16) < 1e-9
    assert put.gamma is None and put.implied_volatility is None  # -999 sentinels dropped


def test_polygon_mapping_and_parse():
    assert polygon_underlying("SPX") == "I:SPX" and polygon_underlying("SPY") == "SPY"
    results = [
        {
            "details": {
                "contract_type": "call",
                "strike_price": 5900,
                "expiration_date": "2026-06-18",
                "ticker": "O:SPX...",
            },
            "greeks": {"gamma": 0.001},
            "implied_volatility": 0.16,
            "open_interest": 1000,
            "day": {"volume": 5},
        },
        {
            "details": {"contract_type": "put", "strike_price": 5800, "expiration_date": "2026-06-18"},
            "greeks": {"gamma": 0.001},
            "implied_volatility": 0.17,
            "open_interest": 2000,
            "day": {"volume": 7},
        },
    ]
    contracts = parse_polygon_results(results, "SPX", 5850.0)
    assert len(contracts) == 2
    assert contracts[0].option_type is OptionType.CALL and contracts[0].open_interest == 1000
    # index spot lives under underlying_asset.value; equities under .price
    assert underlying_spot([{"underlying_asset": {"value": 5850.0}}]) == 5850.0
    assert underlying_spot([{"underlying_asset": {"price": 756.5}}]) == 756.5
    # tolerate the object missing on early items, find it later
    assert underlying_spot([{}, {"underlying_asset": {"value": 42.0}}]) == 42.0


def test_thetadata_roots_and_parse():
    assert roots_for("SPX") == ["SPX", "SPXW"] and roots_for("SPY") == ["SPY"]
    greeks_payload = {
        "header": {"format": ["ms_of_day", "gamma", "implied_vol", "underlying_price"]},
        "response": [
            {
                "contract": {"root": "SPXW", "expiration": 20260618, "strike": 5900000, "right": "C"},
                "ticks": [[1, 0.001, 0.16, 5850.0]],
            },
            {
                "contract": {"root": "SPXW", "expiration": 20260618, "strike": 5800000, "right": "P"},
                "ticks": [[1, 0.001, 0.17, 5850.0]],
            },
        ],
    }
    oi_payload = {
        "header": {"format": ["ms_of_day", "open_interest", "date"]},
        "response": [
            {
                "contract": {"root": "SPXW", "expiration": 20260618, "strike": 5900000, "right": "C"},
                "ticks": [[1, 1000, 20260529]],
            },
        ],
    }
    snap = parse_theta_bulk(greeks_payload, oi_payload, "SPX")
    assert snap.spot == 5850.0 and len(snap.contracts) == 2
    call = next(c for c in snap.contracts if c.option_type is OptionType.CALL)
    assert call.strike == 5900.0 and call.open_interest == 1000 and call.gamma == 0.001


def test_thetadata_fixed_format_fallback():
    # No header.format -> parser must fall back to the documented column order of
    # greeks_second_order: [ms_of_day,bid,ask,gamma,vanna,charm,vomma,veta,
    #                        implied_vol,iv_error,ms_of_day2,underlying_price,date]
    greeks_payload = {
        "response": [
            {
                "contract": {"root": "SPXW", "expiration": 20260618, "strike": 5900000, "right": "C"},
                "ticks": [[1, 1.0, 1.2, 0.0021, 0, 0, 0, 0, 0.16, 0, 1, 5850.0, 20260529]],
            },
        ],
    }
    oi_payload = {  # OI fixed order: [ms_of_day, open_interest, date]
        "response": [
            {
                "contract": {"root": "SPXW", "expiration": 20260618, "strike": 5900000, "right": "C"},
                "ticks": [[1, 1234, 20260529]],
            },
        ],
    }
    snap = parse_theta_bulk(greeks_payload, oi_payload, "SPX")
    c = snap.contracts[0]
    assert snap.spot == 5850.0 and c.gamma == 0.0021
    assert abs(c.implied_volatility - 0.16) < 1e-9 and c.open_interest == 1234


def test_tastytrade_nested_parse_compact_and_build():
    nested = {
        "data": {
            "items": [
                {
                    "expirations": [
                        {
                            "expiration-date": "2026-06-18",
                            "strikes": [
                                {
                                    "strike-price": "5900.0",
                                    "call-streamer-symbol": ".SPXW260618C5900",
                                    "put-streamer-symbol": ".SPXW260618P5900",
                                },
                            ],
                        }
                    ]
                }
            ]
        }
    }
    chain = parse_nested_chain(nested)
    assert len(chain) == 2 and chain[0].streamer_symbol == ".SPXW260618C5900"

    # COMPACT feed: Greeks has 4 fields, Summary 3.
    feed = ["Greeks", ["Greeks", ".SPXW260618C5900", 0.001, 0.16], "Summary", ["Summary", ".SPXW260618C5900", 1000]]
    records = parse_compact_feed(feed, {"Greeks": 4, "Summary": 3})
    assert ("Greeks", ["Greeks", ".SPXW260618C5900", 0.001, 0.16]) in records

    snap = build_snapshot(
        chain,
        greeks_by_sym={".SPXW260618C5900": {"gamma": 0.001, "volatility": 0.16}},
        oi_by_sym={".SPXW260618C5900": 1000},
        spot=5850.0,
        symbol="SPX",
    )
    call = next(c for c in snap.contracts if c.option_type is OptionType.CALL)
    assert call.gamma == 0.001 and call.open_interest == 1000


def test_parse_occ_symbol_rejects_malformed():
    import pytest
    from spotgamma.sources.occ import parse_occ_symbol

    with pytest.raises(ValueError):
        parse_occ_symbol("GARBAGE")
    with pytest.raises(ValueError):
        parse_occ_symbol("SPX260618X00200000")  # 'X' is not a valid right
