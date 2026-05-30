# Data Sources — wiring your account

The engine reads chains through a vendor-neutral `ChainSource`
(`engine/spotgamma/sources/`). Every adapter normalizes its provider's response
into a `ChainSnapshot`; the gamma math never imports a vendor SDK. Pick a source
with `--source <name>` (CLI) or `SPOTGAMMA_SOURCE` (API).

```bash
spotgamma levels SPX --source cboe          # free, no key — works today
SPOTGAMMA_SOURCE=schwab uvicorn api.main:app
```

## What the engine needs per contract
Full chain by **expiration × strike**, call/put, **open interest**, **gamma** (or
IV so we compute it via Black-Scholes), plus underlying **spot**. The hardest
filter is **SPX/NDX cash-settled index options** — many retail brokers only do
SPY/QQQ ETFs — and the recurring trap is the **SPXW** weekly/0DTE root.

## Shipped adapters

| `--source` | Type | Greeks/gamma | OI | SPX/NDX | Auth / env | Cost | Status |
|---|---|---|---|---|---|---|---|
| `sample` | fixtures | ✅ | ✅ | ✅ | none | free | tested |
| `cboe` | free CDN | ✅ | ✅ | ✅ (+SPXW) | none | $0 (15-min delayed) | **verified live** |
| `tradier` | broker | ✅ (ORATS, EOD) | ✅ | ✅ | `TRADIER_TOKEN` | free w/ funded acct | needs creds |
| `schwab` | broker | ✅ native | ✅ | ✅ | `SCHWAB_ACCESS_TOKEN` (OAuth2) | free w/ acct | needs creds |
| `polygon` | vendor | ✅ | ✅ | ✅ (`I:SPX`) | `POLYGON_API_KEY` | $29–199/mo | needs key |
| `thetadata` | vendor (local) | ✅ | ✅ | ✅ (SPXW) | Theta Terminal @ `THETADATA_URL` | $40–160/mo | needs terminal |
| `tastytrade` | broker (stream) | ✅ via DXLink | ✅ | ✅ | `TASTYTRADE_USERNAME`/`_PASSWORD` | free w/ acct | experimental |

Parsing for every adapter is a pure function with unit tests
(`engine/tests/test_sources.py`); the network paths for credentialed sources
need live verification with your account.

### cboe (recommended starting point)
Zero cost, no signup. Public delayed-quotes JSON
(`cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json`) returns the whole
chain — gamma, IV, OI, SPX **and** SPXW — ~15-min delayed. Verified live:
30,970 SPX contracts, spot+greeks+OI all present. Unofficial endpoint; Cboe ToS
restricts automated scraping, so this is for personal research, not
redistribution.

### tradier / schwab (free with a brokerage account)
One REST call returns greeks+IV+OI. **Schwab** greeks are native and the fullest;
**Tradier** sources greeks from ORATS (end-of-day modeled, not live ticks). Schwab
needs a developer app approval (1–3 days) and OAuth2; refresh tokens last 7 days.
Index symbols: Tradier plain `SPX` (+ `includeAllRoots` for `SPXW`); Schwab
`$SPX`/`$NDX.X`.

### polygon / thetadata (paid vendors, real-time)
**Polygon** snapshot (`/v3/snapshot/options/I:SPX`) bundles OPRA for retail tiers;
greeks/real-time on paid Options plans. **ThetaData** runs a local Terminal gateway
(no key in-adapter) and bundles real-time OPRA cheaply ($40–160/mo); index SPX
spans roots `SPX`+`SPXW`.

### tastytrade (free, streaming — experimental)
REST chain returns only metadata + dxFeed streamer-symbols; gamma/IV arrive over a
**DXLink websocket** (Greeks events), OI over Summary events. Adapter logs in,
pulls a quote token, subscribes, and collects a snapshot with a timeout. Needs the
`stream` extra (`websockets`) and a funded account; live path is untested here.

## OPRA fees (why "delayed" is free)
Real-time US options data is licensed by OPRA per subscriber. **15-min delayed and
historical (≥1 day old) data carry no per-user OPRA fee** — which is exactly why
the `cboe` delayed feed and broker delayed tiers are free, while real-time vendors
(Polygon real-time, Databento, dxFeed) pass through or bundle OPRA (~$1.25/mo
non-pro display, ~$31.50/mo professional, +$1,500/mo redistributor).

## Not shipped (researched, lower fit)
Alpaca & Webull data API (**no SPX/NDX** — ETF only), Robinhood (index options but
**unofficial** API / ToS risk), E*TRADE & Moomoo (index coverage unverified),
ORATS/MarketData.app/IVolatility/Intrinio (good vendors — easy to add as adapters
later), Databento (raw OPRA, **compute greeks locally**), yfinance (**no gamma**).

## Adding a new source
Implement `ChainSource.get_chain(symbol) -> ChainSnapshot` in a new
`sources/<name>.py`, factor the JSON→model mapping into a pure function, register
it in `sources/base.py::_SOURCES`, and add a parser test. See `cboe.py` as the
reference.
