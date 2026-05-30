"""Generate realistic sample option chains for the offline `sample` source.

Produces ``engine/tests/fixtures/{symbol}_chain.json`` for SPX, NDX, SPY, QQQ.
Each chain has:
  * a strike grid centered on spot,
  * Black-Scholes gamma per contract (so snapshot gamma is internally consistent),
  * an open-interest profile with deliberate bumps that create a call wall above
    spot and a put wall below spot, and a positive net-gamma regime near spot
    that flips negative on the downside (so a Zero Gamma crossing exists).

These are synthetic but structurally faithful; they are NOT market data.
"""

from __future__ import annotations

import json
import math

# Reuse the engine's own Black-Scholes so fixture gamma matches snapshot gamma.
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spotgamma.greeks import bs_gamma

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

# symbol -> (spot, strike_step, num_strikes_each_side, base_iv, call_wall_off, put_wall_off)
SYMBOLS = {
    "SPX": (5850.0, 25.0, 24, 0.16, 150.0, -150.0),
    "NDX": (20500.0, 100.0, 24, 0.18, 600.0, -600.0),
    "SPY": (585.0, 2.5, 24, 0.15, 15.0, -15.0),
    "QQQ": (498.0, 2.5, 24, 0.17, 12.0, -12.0),
}

# Three expirations: 0DTE, this week, and a monthly.
EXPIRY_OFFSETS_DAYS = [0, 4, 25]


def _oi(strike: float, spot: float, call_wall: float, put_wall: float, is_call: bool) -> int:
    """Open-interest profile: broad base + a wall bump on the right side."""
    base = 1500 * math.exp(-((strike - spot) ** 2) / (2 * (spot * 0.04) ** 2))
    if is_call:
        bump = 9000 * math.exp(-((strike - call_wall) ** 2) / (2 * (spot * 0.006) ** 2))
    else:
        bump = 9000 * math.exp(-((strike - put_wall) ** 2) / (2 * (spot * 0.006) ** 2))
    return int(base + bump)


def build(symbol: str) -> dict:
    spot, step, n, iv, cw_off, pw_off = SYMBOLS[symbol]
    today = date(2026, 5, 29)  # a Friday -> 0DTE is meaningful
    ts = datetime(2026, 5, 29, 15, 0, 0)
    call_wall, put_wall = spot + cw_off, spot + pw_off
    strikes = [spot + (i - n) * step for i in range(2 * n + 1)]

    contracts = []
    for off in EXPIRY_OFFSETS_DAYS:
        exp = today + timedelta(days=off)
        t = max(off, 0.3) / 365.0  # floor so 0DTE gamma is finite, not a spike
        for k in strikes:
            # mild vol smile: cheaper wings stabilize the curve shape
            smile = iv * (1 + 0.15 * (abs(k - spot) / spot))
            g = bs_gamma(spot, k, t, smile)
            for is_call in (True, False):
                oi = _oi(k, spot, call_wall, put_wall, is_call)
                if oi <= 0:
                    continue
                contracts.append(
                    {
                        "option_type": "call" if is_call else "put",
                        "strike": round(k, 2),
                        "expiration": exp.isoformat(),
                        "open_interest": oi,
                        "volume": int(oi * 0.3),
                        "gamma": round(g, 10),
                        "implied_volatility": round(smile, 4),
                    }
                )

    return {
        "symbol": symbol,
        "spot": spot,
        "timestamp": ts.isoformat(),
        "risk_free_rate": 0.04,
        "contracts": contracts,
    }


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for sym in SYMBOLS:
        path = FIXTURE_DIR / f"{sym.lower()}_chain.json"
        path.write_text(json.dumps(build(sym), indent=2))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
