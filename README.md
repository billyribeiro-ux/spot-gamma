# Spot Gamma

Institutional-grade spot-gamma system with a clean separation of concerns:

```
┌──────────────┐    ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│ Chain source │ →  │   Engine    │ →  │   FastAPI    │ →  │  SvelteKit   │
│ sample/live  │    │ GEX + levels│    │  /levels/{}  │    │  dashboard   │
└──────────────┘    └─────────────┘    └──────────────┘    └──────────────┘
                          │
                          └─→ ThinkScript export (display-only overlay)
```

- **The Python engine calculates gamma** — the single source of truth.
- **The dashboard validates and displays it.**
- **ThinkScript only renders finished levels** (it cannot ingest a live chain).

Methodology — every formula and assumption — lives in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md). Read it first.

Symbols: **SPX, NDX, SPY, QQQ**. Runs fully offline on sample fixtures (no API
key); live data is opt-in.

## Quickstart

### 1. Engine (offline, no key)

```bash
cd engine
pip install -e .
pytest                                   # 26 tests
spotgamma levels SPX --source sample     # print computed levels JSON
spotgamma export-thinkscript SPX         # write thinkscript/spot_gamma_spx.ts
```

### 1b. Real data, free, no account

```bash
pip install -e "engine[live]"
spotgamma levels SPX --source cboe        # live SPX (~15-min delayed) from Cboe
```

### 2. API

```bash
pip install -e "engine[api]"
PYTHONPATH=engine uvicorn api.main:app --port 8000
curl localhost:8000/levels/SPX
```

### 3. Dashboard

```bash
cd dashboard
npm install
npm run dev        # http://localhost:5173 (proxies /api -> :8000)
```

The dashboard polls the API every 30s and renders regime, key levels, the
net-gamma-by-strike heatmap (call wall / put wall / vol trigger), per-expiry
gamma, 0DTE concentration, and a copy-paste ThinkScript block.

### Connections hub (`/admin`)

Open `http://localhost:5173/admin` to wire data sources without touching env
vars: paste each provider's API credentials, **Test connection** (a live backend
probe — auth/reachability), and **Set active** to pick which source feeds the
dashboard. `cboe` needs no credentials, so you can set it active and run real
(15-min delayed) data immediately. Credentials are saved server-side to a
gitignored `instance/credentials.json` (0600), and secret values are never sent
back to the browser. This is a **local, single-user admin** — don't expose the
API to untrusted networks. Endpoints: `GET/PUT /admin/sources`,
`POST /admin/sources/{name}/test`, `PUT /admin/active/{name}`.

### Going live / wiring your account

Multiple data sources are pluggable behind one `ChainSource` interface — pick the
one matching the account you have. Full comparison and the research behind it:
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

```bash
spotgamma levels SPX --source cboe        # free, no key (15-min delayed)

export TRADIER_TOKEN=...                   # broker, greeks+OI (ORATS, EOD)
export SCHWAB_ACCESS_TOKEN=...             # broker, native greeks (OAuth2)
export POLYGON_API_KEY=...                 # vendor, real-time (paid)
# thetadata: run Theta Terminal locally (THETADATA_URL, default :25510)
# tastytrade: TASTYTRADE_USERNAME/_PASSWORD  (pip install -e "engine[stream]")

spotgamma levels SPX --source schwab
SPOTGAMMA_SOURCE=cboe uvicorn api.main:app --port 8000
```

Sources: `sample`, `cboe`, `tradier`, `schwab`, `polygon`, `thetadata`, `tastytrade`.

## Layout

| Path | What |
|---|---|
| `docs/METHODOLOGY.md` | Formulas, level definitions, dealer assumption, validation protocol. |
| `docs/DATA_SOURCES.md` | Broker/vendor comparison + how to wire each adapter. |
| `engine/spotgamma/` | Models, greeks, GEX, profile, levels, sources, CLI, ThinkScript export. |
| `engine/tests/` | Unit tests + `fixtures/*_chain.json` sample chains. |
| `engine/tools/make_fixtures.py` | Regenerate the sample chains. |
| `api/main.py` | FastAPI service over the engine. |
| `dashboard/` | SvelteKit dashboard (Svelte 5 runes). |
| `thinkscript/` | Generated Thinkorswim overlays. |

## Status

MVP covering all four agreed phases (methodology, engine, API+dashboard,
ThinkScript). The broader Market-Structure system (VIX, yields, DXY, breadth,
seasonality) is out of scope here and structured to extend later.

> Sample fixtures are synthetic and **not market data**. Spot gamma is an
> inference, not certainty — see the disclaimer in the methodology doc.
