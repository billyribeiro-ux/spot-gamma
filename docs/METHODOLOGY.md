# Spot Gamma Methodology

This document is the **source of truth** for how the engine turns an options
chain into dealer-facing gamma levels. Every number the dashboard or ThinkScript
shows is defined here so the output is reproducible and auditable. It is the
Phase 1 deliverable: methodology first, code second.

> **Disclaimer.** Spot gamma is an *inference* from public open interest and
> greeks under an assumption about dealer positioning. Nobody can observe true
> dealer books from public data. The goal is consistent, repeatable estimation —
> not certainty.

---

## 1. Dealer positioning assumption

We assume **dealers are long calls and short puts** (the standard naive
convention, a.k.a. the SqueezeMetrics convention). Consequently:

- **Call gamma → positive** GEX contribution
- **Put gamma → negative** GEX contribution

This is an assumption, not an observation. It is the single most important
modeling choice; all levels below inherit it. A future refinement could weight by
a positioning model (e.g. customer-buys-puts skew), but the MVP keeps the
transparent naive convention.

Implemented in `engine/spotgamma/gex.py::contract_gex` (sign by option type).

## 2. Contract-level dollar gamma exposure

For each contract *i*:

```
GEX_i = gamma_i × OI_i × multiplier × spot² × 0.01
```

- `gamma_i` — per-share Black-Scholes gamma (from the data source, or computed).
- `OI_i` — open interest (contracts outstanding).
- `multiplier` — **100** for SPX, NDX, SPY, QQQ.
- `spot²` — converts share gamma to dollar gamma notional.
- `0.01` — expresses the result **per 1% move** in spot.

Interpretation: the dollar notional of the underlying dealers must trade to stay
delta-neutral for a 1% move. **+$1B net GEX** ≈ dealers buy/sell ~$1B per 1%.

## 3. Snapshot vs. profile (why we need both)

- **Snapshot** — use each contract's gamma at the *current* spot. Drives Net GEX,
  the regime tag, walls, and per-strike/per-expiry aggregates. Uses source gamma
  when available (`gex.py`).
- **Profile** — recompute every contract's gamma via Black-Scholes across a grid
  of hypothetical spot levels (default ±15%, 121 steps) and sum to a net-GEX
  curve. Required to locate **Zero Gamma** honestly, because dealer gamma changes
  as price moves. Implemented in `engine/spotgamma/profile.py`, with one
  consistent BS basis at every grid point (no source-gamma shortcut mid-curve).

### Numerical details

- **Carry-adjusted (Merton) gamma** — the BS fallback/profile use a continuous
  dividend yield `q`: drift is `(r − q)` in `d1` and gamma carries the `e^{−qT}`
  factor. `q` defaults to 0 (plain BS); set `ChainSnapshot.dividend_yield` for
  index carry.
- **Zero Gamma refinement** — the grid gives a linear estimate (~0.25% resolution
  at 121 steps); the chosen crossing is then refined by **bisection** on the real
  net-GEX curve, so the level isn't capped by grid spacing.
- **IV normalization** — vendors disagree on units (Schwab/ORATS emit percent
  points, others decimals); every adapter routes IV through `normalize_iv`, which
  converts percent→decimal heuristically and drops sentinels/NaN.
- **ET session calendar** — DTE and 0DTE are anchored to the US/Eastern trading
  date, not UTC, to avoid an after-hours off-by-one.

Black-Scholes gamma (`engine/spotgamma/greeks.py`) is also the **fallback** when a
source provides IV but not gamma. Gamma is identical for a call and put at the
same strike/expiry/vol, so one function serves both.

## 4. Level definitions

All computed in `engine/spotgamma/levels.py`. Walls key on **net** GEX per strike
(call + put) rather than raw call/put gamma, so the near-ATM 0DTE gamma spike —
where call and put gamma cancel — does not masquerade as a wall.

| Level | Definition |
|---|---|
| **Net GEX** | Sum of signed `GEX_i` across the chain. |
| **Regime** | `positive` if Net GEX ≥ 0 (dealers long gamma, dampening, mean-reverting), else `negative` (short gamma, amplifying, trending). |
| **Zero Gamma** | Spot level where the **profile** net-GEX curve crosses zero, linearly interpolated; the crossing nearest current spot. `None` if no flip in range. The gamma "flip". |
| **Call Wall** | Strike with the largest **positive** net GEX at/above spot — resistance, where dealers sell into strength. |
| **Put Wall** | Strike with the largest **negative** net GEX at/below spot — support, where dealers buy weakness. |
| **Volatility Trigger** | The listed **strike nearest Zero Gamma** — the actionable, tradable version of the flip. Distinct from Zero Gamma (continuous) by being strike-snapped. |
| **Absolute Gamma** | Strike with the most **total** gamma (`\|call GEX\| + \|put GEX\|`, side-agnostic) — the single largest gamma concentration / strongest pin. Differs from the walls (net GEX) because near-ATM strikes can stack large call *and* put gamma. |
| **Hedge Wall** | Strike with the largest **net** dealer-gamma magnitude (`max \|net GEX\|`), whichever side of spot — the dominant hedging wall. Often coincides with the Call or Put Wall when one side clearly dominates. |
| **Top positive/negative nodes** | Strikes ranked by net GEX, the biggest long- and short-gamma concentrations. |
| **By expiry** | Net GEX summed per expiration. |
| **0DTE concentration** | Share of total `|GEX|` sitting in options expiring today, plus 0DTE net GEX. |

> **Note on Volatility Trigger / Absolute Gamma / Hedge Wall.** SpotGamma's
> Volatility Trigger™, Absolute Gamma, and Hedge Wall are proprietary and not
> identical to these. We define transparent, public-methodology proxies (above)
> and treat them as documented approximations, to be refined during Phase 3
> validation — never silently tuned to match a vendor.

## 5. Symbol nuances

| Symbol | Type | Settlement | Notes |
|---|---|---|---|
| **SPX** | Index | Cash, AM (monthly) / PM (weeklies, 0DTE) | Canonical reference. Largest notional. |
| **NDX** | Index | Cash | Nasdaq-100; ~3.5× SPX price, coarse strikes. |
| **SPY** | ETF | Physical | ~1/10 SPX. Finer strikes, retail noise, more 0DTE. |
| **QQQ** | ETF | Physical | Nasdaq-100 ETF; retail-heavy. |

**Expiry handling.** All listed expirations are included in aggregate Net GEX,
walls, and Zero Gamma. We additionally break out **0DTE** (expires today) because
its gamma is large, fast-decaying, and concentrates near ATM, dominating intraday
pinning. 0DTE is reported separately rather than excluded.

**0DTE gamma floor.** True 0DTE ATM gamma approaches a spike near expiry. The
engine floors time-to-expiry in profile/fallback BS to keep gamma finite and the
aggregates numerically stable.

## 6. Data sources

The engine is vendor-neutral behind `ChainSource` (`engine/spotgamma/sources/`).
A source normalizes any vendor's chain into a `ChainSnapshot`; gamma math never
imports a vendor SDK.

- **`sample`** (default) — JSON fixtures, fully offline. Powers tests, CLI, API,
  dashboard with no key. Synthetic but structurally faithful; **not market data**.
- **`cboe`** — free, no key; Cboe delayed-quotes JSON with gamma/IV/OI incl. SPXW.
- **`tradier` / `schwab`** — brokerage APIs, greeks+OI in one REST call.
- **`polygon` / `thetadata`** — paid vendors, real-time OPRA-bundled greeks.
- **`tastytrade`** — broker; greeks stream over DXLink (experimental).

See [`DATA_SOURCES.md`](DATA_SOURCES.md) for the full comparison and the research
behind these choices (and why Alpaca/Webull/yfinance were not shipped).

## 7. Validation protocol (Phase 3)

Methodology is only trustworthy if calibrated against the field. For each symbol,
on the same timestamp, record our Zero Gamma, Call Wall, Put Wall, and regime vs:

- **SpotGamma**, **GammaEdge**, **MenthorQ**.

Expectations:
- **Walls** should land on the same major strikes (exact match common).
- **Zero Gamma / flip** within a small band; method differences (vendor
  positioning models, OI vs. dealer-adjusted) explain residual divergence.
- **Regime sign** should agree the large majority of the time.

Persistent large divergence is a signal to revisit the positioning assumption
(§1) or the Volatility Trigger proxy (§4), **not** to silently tune to match.

## 8. Out of scope (MVP)

The broader Market-Structure system (VIX, bond yields, DXY, breadth, seasonality,
economic-calendar risk) is intentionally excluded here. The engine/API are
structured so these become additional panels/endpoints later. See §10 for the
phased plan; it begins with research, not code.

## 9. Phase 4 — Thinkorswim integration (done)

The engine renders a Thinkorswim study from the computed levels
(`export_thinkscript.py`), served three ways: the CLI
(`spotgamma export-thinkscript SPX`), the API (`GET /thinkscript/{symbol}`,
plain text), and the dashboard panel (which fetches the API so its copy is
byte-identical — one source of truth). Numbers are proven first (§7); ThinkScript
is display-only and cannot ingest a chain, so it carries the engine's outputs.

Shipped:
- **Support/resistance lines & gamma walls** — Call/Put Wall, Abs Gamma, Hedge
  Wall as horizontal plots; colors match the dashboard ($lib/levels).
- **Flip zone** — a shaded `AddCloud` band between Gamma Flip and Vol Trigger.
- **Regime dashboard + color-coded background** — `AddLabel` row (symbol, regime,
  net GEX, 0DTE%) plus `AssignBackgroundColor` tinting green (positive/pinning) or
  red (negative/trending).
- **Alert conditions** — `Crosses(close, level)` alerts on Call Wall, Put Wall,
  and Gamma Flip, gated behind an `enableAlerts` input (quiet by default).

## 10. Phase 5 — Market-Structure intelligence (research first)

The long-term goal is an institutional **Market Structure Dashboard** that fuses
gamma with the rest of the regime picture: **VIX / term structure, bond yields,
DXY, market breadth, dealer positioning, volatility regime, gap statistics,
seasonality, and economic-calendar risk.**

This is explicitly **research-gated** — the methodology document comes before any
code, because the synthesis logic (how these combine into a single read) is what
determines whether the result is genuinely useful or just more dials. Planned
sequence:

1. **Research + methodology doc** — for each signal: definition, free/licensed
   data source (reuse the `ChainSource`-style adapter pattern), normalization,
   and how it maps to a regime score. Document confounders and what *not* to
   over-claim.
2. **Composite regime model** — a transparent, weighted/rules-based score (not a
   black box), with each input independently inspectable.
3. **Backtest/validation** — does the composite add information over gamma alone?
4. **UI** — only then, a dashboard surface.

Nothing here is built yet; this section is the contract for how it will be.
