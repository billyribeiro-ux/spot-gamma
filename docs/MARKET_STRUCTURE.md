# Market Structure — methodology (Phase 5)

> **Status: research + methodology. This document gates the code.** Every
> threshold, weight, and combination rule below is written *before* it appears in
> the engine, and the engine must cite this doc. The point of writing it first is
> intellectual honesty — a market-structure read is only useful if the synthesis
> logic is defensible, not just another pile of dials.

The gamma engine (`docs/METHODOLOGY.md`) answers *"where will dealer hedging pin
or amplify price today?"* — a mechanical, intraday-to-weekly signal. The
**Market Structure** layer answers a different, slower question: *"what regime is
the market in?"* — risk-on vs risk-off, calm vs stressed, mean-reverting vs
trending. It fuses cross-asset, volatility, and (later) breadth/positioning
signals into a transparent regime read that **conditions** how the gamma levels
should be traded.

## 0. First principles (read these before any number)

1. **Macro/vol signals are a *regime prior*, not a tactical trigger.** They set
   the backdrop bias (risk-on/off); gamma sets the levels and timing. Long,
   variable lead times make them unsuitable as same-day signals.
2. **Correlations are regime-dependent and flip.** The dollar↔equity sign, the
   stock↔bond correlation, the curve's lead/lag — all change across cycles.
   Never hard-code a single permanent sign. We z-score and orient per-signal, and
   we surface divergence as its own warning.
3. **Levels vs rate-of-change.** Only the yield curve has a meaningful *level*
   threshold (inversion < 0). The dollar and credit spreads are primarily
   **direction/momentum** signals; their absolute level can sit "low" for years.
4. **Everything mean-reverts and drifts.** VIX, VVIX, spreads all revert around
   era-dependent means. Fixed thresholds need periodic recalibration; where
   possible we score by rolling z-score/percentile, not absolutes.
5. **Bands are practitioner convention, not law.** CBOE/Fed *define and publish*
   the series; the regime cut-points (VIX < 15 = calm, etc.) are widely-used
   heuristics. We treat them as soft zones and say so.
6. **Don't over-claim.** Where an effect is weak, faded, or overfit
   (most seasonality), we shrink it hard and label it. A signal we can't source
   cleanly for free (breadth, equity put/call) is documented as a **planned
   extension**, not faked.

## 1. Data sources (all free, no API key — probed live 2026-05-30)

| Source | How | Series |
|---|---|---|
| **Yahoo v8 chart** | `query1.finance.yahoo.com/v8/finance/chart/{ticker}` (browser UA) | `^VIX`, `^VIX3M`, `^VVIX`, `^TNX`, `DX-Y.NYB`, OHLC |
| **FRED CSV** | `fred.stlouisfed.org/graph/fredgraph.csv?id={ID}` (library UA — **opposite** UA to Yahoo) | `DGS10`, `T10Y2Y`, `T10Y3M`, `BAMLH0A0HYM2`, `DTWEXBGS`, `VIXCLS`, `VXVCLS` |
| **Derived** | from the calendar date + OHLC we already fetch | gap stats, seasonality, event flags |

**Not freely available** (documented as gaps, not faked): a pre-built S&P 500
breadth index (`$SPXA50R` etc. are StockCharts/Barchart-gated, not on Yahoo) and
a live **equity** put/call ratio (FRED's series ended 2019-10; CBOE's JSON 403s
us). Both are buildable later by self-computing from ~500 constituents / Yahoo
option-chain volumes — see §7.

## 2. Volatility signals

### 2.1 VIX level
- **Definition.** CBOE 30-day forward implied vol of the S&P 500 (variance-swap
  replication over an SPX option strip), annualized %. **Mean-reverting** around
  an era-dependent long-run mean (~19–20).
- **Bands (practitioner convention).** `<15` calm/complacent · `15–20` normal ·
  `20–30` elevated · `30–40` fear · `>40` crisis.
- **Regime implication.** Low → risk-on, low realized vol, trend-friendly. High →
  risk-off. **Extreme** high is contrarian-bullish forward (VIX mean-reverts and
  peaks cluster near price bottoms) → use VIX as a *state descriptor*, not a
  directional timer.
- **Source.** Yahoo `^VIX`; FRED `VIXCLS`.
- **Caveats.** Level alone is a poor timer (term structure carries more); embeds
  a variance risk premium (structurally above realized vol); thresholds drift.

### 2.2 VIX term structure (VIX / VIX3M)
- **Definition.** Ratio of 30-day VIX to 3-month VIX3M (renamed from VXV, 2017).
  `<1` = contango (calm, ~80% of the time); `>1` = backwardation (acute stress);
  `>1.10` = deep stress/panic.
- **Regime implication.** The **flip from contango to backwardation is one of the
  more reliable regime-change markers** — more informative than the VIX *level*
  for timing, because it captures the *shape* of fear. Contango = risk-on default;
  backwardation = risk-off / dislocation.
- **Source.** Yahoo `^VIX` & `^VIX3M` (compute ratio); FRED `VIXCLS` & `VXVCLS`.
- **Caveats.** Whipsaws around 1.0 (smooth or use a buffer). The catastrophic tail
  (Volmageddon, Feb 2018) is exactly a violent contango→backwardation snap —
  the signal "works until it doesn't," so it informs *regime*, never position size
  alone.

### 2.3 VVIX (vol of vol)
- **Definition.** "VIX of the VIX" — 30-day expected vol of VIX from VIX options.
  Long-run avg ~85; `<90` calm, `>120` elevated, `>150` crisis.
- **What it adds.** Distinguishes **low-and-stable from low-and-fragile** vol.
  Elevated/rising VVIX while spot VIX stays low = surface calm, tail uncertainty
  building (this divergence preceded Volmageddon). Strongest academic anchor:
  **Fed FEDS 2013-54** (higher VVIX predicts lower SPX put returns 3–4 weeks out).
- **Source.** Yahoo `^VVIX` (not on FRED).
- **Caveats.** Noisy standalone; value is *relative to VIX* (divergence/ratio),
  not absolute level. Thin underlying (VIX options) → dealer-positioning artifacts.

### 2.4 Volatility regime (composite of 2.1–2.3)
A transparent rule-based label — **calm / normal / stressed / crisis** — from VIX
level × term-structure sign × VVIX, e.g.:

| | contango (ratio<1) | backwardation (ratio≥1) |
|---|---|---|
| **VIX < 20** | calm (normal if VVIX>120) | stressed |
| **VIX 20–30** | normal | stressed |
| **VIX > 30** | stressed | crisis |

We choose a transparent matrix over an HMM/ML classifier on purpose: regimes
should be *inspectable*. (The literature — Markov-switching GARCH, HMMs — reports
~85–92% in-sample accuracy but is easy to overfit and identifies the regime
*contemporaneously, with a lag at the transitions that matter most.*)

## 3. Macro / cross-asset signals

### 3.1 Yield curve (2s10s) + 10Y level
- **Definition.** `T10Y2Y` = 10Y − 2Y. Inversion (`<0`) is the classic
  recession-risk signal (historical lead 6–24 months). 10Y level (`DGS10`, or
  Yahoo `^TNX`÷10) matters for equities via discount-rate pressure on long-duration
  names (NDX > SPX) and especially the **speed** of moves (rapid >~50bp/month
  spikes are the equity-negative event).
- **Regime implication.** A **recession/regime prior, not an equity sell signal** —
  equities often rise during the inverted window; the drawdown clusters around the
  *un-inversion* + recession onset. Steepening sign depends on *which end moves*
  (bull steepener = late-cycle/risk-off; bear steepener = reflationary/risk-on).
- **Source.** FRED `T10Y2Y`, `DGS10`; Yahoo `^TNX`.
- **Caveats.** **2022–24 is the live counterexample** — 2s10s inverted ~25 months
  with no recession in the window. Term-premium distortion (QE) flattens the
  curve, so a given inversion signals *less* than historically. The Fed prefers
  `T10Y3M` / the near-term forward spread (Engstrom–Sharpe) — 2s10s is the
  *familiar* gauge, not the optimal one. We show 2s10s and disclose this.

### 3.2 US Dollar (DXY)
- **Definition.** ICE Dollar Index (`DX-Y.NYB`), EUR-dominated 6-currency basket.
  Cross-check FRED `DTWEXBGS` (broad, 26-currency — the better *macro tightness*
  gauge). **No fixed level threshold** — directional / rate-of-change. Trend filter:
  vs 200-day MA.
- **Regime implication — the Dollar Smile (Jen).** Non-linear: USD rallies in
  *crisis* (safe haven, risk-off) **and** in *US-outperformance* (rate
  differentials, can be risk-on) — weak USD in the steady-growth middle. So a
  rising dollar is risk-off *or* risk-on depending on which side of the smile.
  Mechanically, sustained/rapid USD strength is a modest equity/earnings headwind
  (~40% of S&P revenue is ex-US) — strongest for multinationals and commodities.
- **Source.** Yahoo `DX-Y.NYB`; FRED `DTWEXBGS`.
- **Caveats.** **The sign flips** (2025 saw an unusual *positive* USD↔SPX
  correlation). DXY ≠ broad dollar. Use trend + rate-of-change + regime label,
  never an absolute level.

### 3.3 Credit spreads (HY OAS)
- **Definition.** ICE BofA US High-Yield OAS (`BAMLH0A0HYM2`, %). `<300bp` tight/
  complacent · `300–500` normal (long-run avg ~490) · `500–600` caution · `>600`
  stress · `>1000` crisis.
- **Regime implication.** One of the cleanest risk-on/off confirmations; credit
  often "sniffs out" stress before equities. Most actionable as **direction**: a
  spread *widening fast off a low base* warns even while numerically low. Tradable
  proxy: HYG/LQD ratio.
- **Source.** FRED `BAMLH0A0HYM2` (+ `BAMLC0A0CM` IG); Yahoo `HYG`/`LQD`.
- **Caveats.** Levels regime-conditioned by the rate environment / reach-for-yield
  (can sit "low" for years). 2023 bank stress didn't push HY > 600bp. Rate-of-change
  > level. The "600bp → recession 85% of the time" stat is one post-1996 backtest.

## 4. Dealer gamma (already computed) — how it composes

We already produce net GEX, the zero-gamma flip, and call/put walls. In the
market-structure read, **gamma is not just another averaged input — it is a
regime *gate*** on a different axis (volatility regime) from the directional
signals:

- **Positive gamma** (spot above flip): dealers sell rallies / buy dips → realized
  vol suppressed, **mean-reverting, pinned** toward walls. *Dampen* directional
  conviction; expect extremes to fade.
- **Negative gamma** (spot below flip): dealers chase → **trending, amplified**,
  breakout-prone. *Amplify* — a fragile macro/vol read becomes dangerous because
  flow accelerates moves.

So gamma enters the composite as a **multiplier on actionability**, plus a
**flip-proximity flag** (near the flip = regime-transition risk). The
highest-conviction calls come from *alignment*: risk-off macro + stressed vol +
negative gamma = "fragile and trending" (strongest risk-off); risk-on + calm vol
+ positive gamma = "pinned and mean-reverting."

## 5. The composite regime score

Two layers, kept **separately inspectable** on the dashboard (never collapsed to a
single opaque number):

1. **Risk-On/Risk-Off (RORO) sub-score** — z-score each available signal over a
   trailing window (1–3y), orient so **+z = risk-off**, then combine. Following the
   KC Fed RORO template (credit + vol + FX + curve). Initial signal set and
   orientation:

   | Signal | Risk-off direction | Weight* |
   |---|---|---|
   | VIX level | high | 0.18 |
   | VIX term structure | backwardation | 0.18 |
   | VVIX (own baseline + divergence) | high | 0.08 |
   | HY OAS (level + rate-of-change) | widening | 0.22 |
   | Breadth (% > 200/50-DMA) | narrow/washed-out | 0.15 |
   | Put/call (z-scored, contrarian) | complacent (low) | 0.05 |
   | DXY trend + RoC | regime-dependent (smile) | 0.08 |
   | 2s10s | (context flag — displayed, **not summed**) | 0.00 |
   | Dealer gamma sign | negative | 0.06 |

   *Weights are an explicit, documented prior — **not** fit to returns (that would
   be overfit on a short sample). They reflect signal reliability: credit, vol and
   **breadth** highest (breadth is mechanically hardest to fake — § breadth
   research); put/call lowest among the summed signals (noisy, drifting baseline,
   contrarian sign-flips are error-prone); the dollar low (sign-flips); the curve
   held out as a **context flag** (slow recession prior, wrong sign intraday). The
   weights renormalize over whichever signals are present, so breadth/put-call/
   gamma being unavailable degrades gracefully. They live in one constant in the
   code and cite this table.

2. **Gamma modifier** — scales *conviction*, **never the sign**, in `[0.5 … 1.5]`
   by net-GEX sign/magnitude and distance to flip (deep positive → 0.5 = pinned,
   fade extremes; deep negative → 1.5 = trending, act harder). Gamma's *directional*
   vote enters the RORO sum once (the 0.15 weight above); the modifier is a separate
   conviction gate on the volatility-regime axis. The two channels are intentional
   (§4): the additive term is gamma's risk-on/off vote, the modifier is how hard to
   act — but the modifier is **never** allowed to flip or amplify the signed
   direction (multiplying a signed score would make negative gamma read "more
   risk-on" in a calm tape, which is nonsensical).

Composite outputs, all surfaced:
- `roro_score ∈ [-1,+1]` — the signed risk-on/off direction (the bias).
- `gamma_modifier ∈ [0.5,1.5]` — the conviction gate.
- `actionability = |roro| × modifier` — how strongly to act.
- `regime_score = sign(roro) × actionability` — signed conviction; preserves the
   RORO sign and only scales magnitude.

**Honesty rules baked in:** (a) show every component and the divergence between
them — *alignment* is the signal, a lone disagreeing component is an instability
warning; (b) multicollinearity is real (VIX, HY OAS, gamma all co-move in stress)
so we don't treat them as independent confirmations; (c) the score describes the
*current* regime — transitions (price crossing the flip) are where it's weakest,
so flip-proximity is flagged explicitly.

## 6. Gaps, seasonality, event risk (derived — no feed)

### 6.1 Gap statistics
`gap_pct = open_t / close_{t-1} − 1`. Same-day fill from daily OHLC alone: gap-up
filled if `low_t ≤ close_{t-1}`; gap-down if `high_t ≥ close_{t-1}`.
- **The "~70% fill" headline is true only as a small-gap artifact.** Fill rate is
  ~90%+ for tiny gaps but collapses to **~30%** for ≥2% gaps. We **always report
  fill rate conditioned on size bucket**, never one blended number.
- Use **SPY**, not `^GSPC` (the SPX cash "open" is a known artifact). Report median
  |gap| (fat tails). Show sample size per bucket.

### 6.2 Seasonality — shrunk hard, labeled
Calendar effects are the poster child for data-snooping (Sullivan-Timmermann-White).
Only effects with **both replication and a mechanism** feed the (small) seasonal
tilt:
- **Turn-of-month** — the one credible effect (Etula et al. "Dash for Cash",
  institutional flows). Primary input.
- **Pre-holiday drift** — weak/decaying, faint tilt only.
- **Excluded from the return score** (display as labeled trivia at most):
  day-of-week (faded since 1990s), Santa Claus (7-day, tiny sample), September
  (small/noisy), Sell-in-May (contested/specification-fragile), OPEX-week
  (a *vol* effect, belongs in §6.3 not the return score).
- The seasonal score's magnitude is **capped small** — a tilt, not a thesis — and
  shown with its sample size / confidence.

### 6.3 Economic-calendar risk — a *dispersion* gate, not direction
A per-day event-risk flag answering "is today/this week a scheduled high-impact
event?" **Hard line between deterministic and feed-required:**
- **Deterministic from the date** (we compute): OPEX = 3rd Friday; triple-witching
  = 3rd Friday of Mar/Jun/Sep/Dec; NFP ≈ first Friday (*heuristic, flagged*);
  NYSE holidays.
- **Feed-required — never formula-faked**: FOMC (Fed schedule), CPI (BLS), PCE/GDP
  (BEA). Hardcoding these from a formula is the biggest correctness trap in the
  module; until a feed is wired they are simply absent, not guessed.
- Event flags gate **volatility/uncertainty** (verifiable: |daily return| is higher
  on FOMC/CPI/NFP days), **not direction**.

## 7. Extensions — logic built, live data deferred

The scoring logic for these is **built and unit-tested** (pure functions); each
is wired into the composite and degrades gracefully until its live data source is
connected. The deferred piece is only the data fetch, not the methodology.

- **Breadth** (`breadth.py`) — `compute_breadth` derives % above 50/200-DMA and a
  constituent advance/decline from per-symbol closes; `breadth_signal` scores it
  (>60% above 200-DMA = broad/risk-on, <40% = narrow/risk-off). **Deferred:** the
  ~500-constituent close fetch (free constituent list + the existing Yahoo OHLC
  pipeline). Weighted 0.15 (highest after credit/vol — hardest to fake).
- **Put/call** (`putcall.py`) — `put_call_proxy` + `zscore` + `put_call_signal`
  build a contrarian, **z-scored** sentiment read (high put/call = fear =
  contrarian risk-on), never absolute thresholds. **Deferred:** summing put vs
  call option-chain volumes from the chain we already pull. Weighted 0.05 (noisy).
- **Event calendar** (`calendar.py`) — `event_risk` is a *dispersion* gate (not
  directional): OPEX/triple-witching/NFP-heuristic/holidays are computed from the
  date; FOMC/CPI/PCE/GDP come from a `scheduled_events` mapping and are **never
  formula-faked**. **Deferred:** wiring the Fed/BLS/BEA schedule file.
- **Seasonality** (`calendar.py`) — `seasonality` emits a small, capped tilt from
  the *credible* effects only (turn-of-month + faint pre-holiday); day-of-week /
  Santa / September / Sell-in-May are excluded from the return score. Fully built.
- **Gap statistics** (`gaps.py`) — `compute_gap_stats` reports **size-conditioned**
  fill rates from daily OHLC (never the misleading blended "70%"). **Deferred:**
  feeding it the SPY daily-OHLC history we already fetch.
- **Calibrated weights / backtest** — ✅ **built** (`spotgamma/learning/`, §7.1).

### 7.1 Self-learning layer — backtest, calibrated weights, return tilt

The `learning/` package answers the standing question — *does the composite add
information, and should the weights be learned rather than assumed?* — under
strict out-of-sample discipline. It is run via `spotgamma backtest` and
`spotgamma learn`, trains on a freshly-fetched ~10y free panel (FRED `VIXCLS`/
`VXVCLS`/`BAMLH0A0HYM2`/`T10Y2Y`/`DTWEXBGS` + Yahoo `^VVIX`/`SPY`), and is
**point-in-time** end to end: features at *t* use only data observable at *t*
(trailing MAs/RoC never peek ahead), labels are forward SPY returns *t→t+h*.

What it found (walk-forward, expanding-window, OOS — see `backtest.py`):

- **The vol/macro composite carries real forward-return information**: OOS
  information coefficient ≈ **+0.05 / +0.10 / +0.18 at 1 / 5 / 20 trading days**.
- **The relationship is *contrarian***. Signals are oriented +1 = risk-off, so a
  *positive* IC means a risk-off reading preceded *higher* forward returns — the
  mean-reversion §2.1 flags for VIX, now measured. A naïve learner would silently
  flip the sign and turn the regime descriptor into a contrarian timer; we do not.
- **Calibrated weights are *rejected*.** Reliability-reweighting the signals
  (∝ |IC|, shrunk to the §5 prior) does **not** beat the documented prior OOS, so
  the live read keeps the §5 weights. The "learning" only deploys if it earns it.
- **A ridge return-tilt is adopted only at the 20d horizon** (OOS IC ≈ 0.06–0.09),
  surfaced as a **separate, explicitly-labeled** forward-return estimate — never
  merged into the regime score, which still describes *state*, not return.

Honesty rules: the regime orientation and weights are unchanged unless a learned
variant beats the prior out-of-sample; every learned artifact records its
adopt/reject decision and the OOS IC behind it; nothing claims to *predict*
returns — these are measured, sample-sized relationships. The artifact lives in
`instance/learned_model.json` (gitignored) and the live read attaches it as a
`learned` overlay only when present.

**Scope of the backtest.** Only the signals with clean *free history* (vol +
macro) are in the one-shot panel; breadth, put/call and the dealer-gamma sign have
no free back-history, so they cannot be backtested from a single fetch.

### 7.2 Feature-log accumulator — compounding to the full signal set

`learning/featurelog.py` closes that gap the only honest way: `spotgamma
record-features` appends the **live, point-in-time scores of every signal**
(breadth / put-call / gamma-sign included) plus spot to a daily JSON log under
`instance/` (gitignored, deduped by date, atomic). Run daily (e.g. cron), it
accrues a genuine history; `log_to_dataset` then turns it into `FeatureRow`s with
forward returns from the logged spot series, so the §7.1 IC / calibration /
walk-forward machinery applies to **all** signals once enough days accumulate.
Point-in-time is automatic — each score was computed live at its own day's close,
and forward returns only read later rows.

**Dollar signal wiring (fix).** The dollar is a direction/momentum signal (§3.2):
without its 200-DMA + 20-day RoC it is permanently neutral. The live read now
fetches DXY daily closes and computes both (point-in-time, degrading to neutral if
the fetch fails), matching the backtest's dollar features exactly — previously the
live read fed `None`/`None`, leaving the dollar inert yet weighted (a small
distortion on every live RORO).

## 8. Build sequence

1. ✅ **Research + this methodology doc** (gates everything).
2. **Data layer** — FRED + Yahoo fetchers with pure, tested parsers.
3. **Signals** — normalize each raw input into a documented regime score (§2–4, 6).
4. **Composite** — the transparent two-layer score (§5).
5. **API + dashboard** — a Market Structure panel, only after the numbers are
   inspectable.

Validation (per `docs/METHODOLOGY.md` §7 spirit): the composite must be **honestly
labeled** — it describes a regime, it does not predict returns — and every
component stays independently visible so a user can disagree with the blend.

## Sources

Volatility: CBOE VIX/VVIX methodology white papers; Fed FEDS 2013-54
(Volatility-of-Volatility and Tail Risk Premiums); FRED VIXCLS/VXVCLS.
Macro: Fed FEDS Notes on the yield curve & recession probabilities;
Engstrom–Sharpe "(Don't Fear) The Yield Curve" (near-term forward spread);
KC Fed RORO Index (rwp24-12) / NBER w31907; Stephen Jen's Dollar Smile;
FRED series T10Y2Y/T10Y3M/DGS10/DTWEXBGS/BAMLH0A0HYM2.
Breadth/positioning: StockCharts/Schwab breadth thresholds; McClellan Financial;
CBOE/FRED put-call data notes.
Gaps/seasonality: Sullivan-Timmermann-White (data-mining/calendar effects);
Etula et al. "Dash for Cash" (turn-of-month); Bouman–Jacobsen (Halloween) and
the Maberly–Pierce rebuttal; QuantifiedStrategies/Trade-That-Swing gap stats;
Fed/BLS/BEA release calendars.
(Full URLs are recorded in the Phase-5 research transcripts.)
