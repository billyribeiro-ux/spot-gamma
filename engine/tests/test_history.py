"""Tests for the price-history module (pure parsing + mappings, no network)."""

import pytest
from spotgamma.history import (
    DEFAULT_TIMEFRAME,
    TIMEFRAMES,
    parse_yahoo_chart,
    resolve_timeframe,
    yahoo_symbol,
)


def test_yahoo_symbol_mapping():
    assert yahoo_symbol("SPX") == "^GSPC"
    assert yahoo_symbol("NDX") == "^NDX"
    assert yahoo_symbol("SPY") == "SPY"  # ETF passes through
    assert yahoo_symbol("QQQ") == "QQQ"


def test_resolve_timeframe_falls_back_to_default():
    assert resolve_timeframe("5m") == ("5m", "5m", "5d")
    assert resolve_timeframe("1D") == ("1D", "1d", "1y")
    # unknown -> default, never crashes
    token, interval, rng = resolve_timeframe("bogus")
    assert token == DEFAULT_TIMEFRAME and (interval, rng) == TIMEFRAMES[DEFAULT_TIMEFRAME]


def test_parse_yahoo_chart_drops_gap_buckets():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "^GSPC",
                        "currency": "USD",
                        "fullExchangeName": "SNP",
                        "regularMarketPrice": 5850.0,
                    },
                    "timestamp": [1000, 2000, 3000],
                    "indicators": {
                        "quote": [
                            {
                                "open": [10.0, None, 12.0],  # middle bucket is a gap
                                "high": [11.0, None, 13.0],
                                "low": [9.0, None, 11.5],
                                "close": [10.5, None, 12.5],
                                "volume": [100, None, 200],
                            }
                        ]
                    },
                }
            ]
        }
    }
    bars, meta = parse_yahoo_chart(payload)
    assert len(bars) == 2  # the null row is skipped
    assert bars[0].time == 1000 and bars[0].close == 10.5
    assert bars[1].time == 3000 and bars[1].open == 12.0
    assert meta["last_price"] == 5850.0 and meta["currency"] == "USD"


def test_parse_yahoo_chart_errors_on_empty():
    with pytest.raises(ValueError):
        parse_yahoo_chart({"chart": {"result": None, "error": {"code": "Not Found"}}})
