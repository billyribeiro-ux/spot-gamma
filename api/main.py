"""FastAPI service exposing computed gamma levels.

Thin wrapper over the engine: it resolves a chain source, computes levels, and
serves the same :class:`GammaLevels` JSON the CLI emits. Results are cached per
(symbol, source) for a short TTL so the dashboard can poll without recomputing
or re-hitting a live provider on every request.

Run::

    uvicorn api.main:app --reload --port 8000
    curl localhost:8000/levels/SPX
"""
from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from spotgamma.levels import compute_levels
from spotgamma.models import GammaLevels
from spotgamma.sources.base import get_source

# Default source is offline-friendly; override with SPOTGAMMA_SOURCE=tradier.
DEFAULT_SOURCE = os.environ.get("SPOTGAMMA_SOURCE", "sample")
CACHE_TTL = float(os.environ.get("SPOTGAMMA_CACHE_TTL", "30"))
SYMBOLS = ["SPX", "NDX", "SPY", "QQQ"]

app = FastAPI(title="Spot Gamma API", version="0.1.0")
# Dashboard runs on a different origin in dev; allow browser fetches.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache: dict[tuple[str, str], tuple[float, GammaLevels]] = {}


def _get_levels(symbol: str, source: str) -> GammaLevels:
    key = (symbol.upper(), source)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        levels = compute_levels(get_source(source).get_chain(symbol))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:  # source/network/validation errors surface as 502
        raise HTTPException(status_code=502, detail=f"{source} source error: {e}") from e
    _cache[key] = (now, levels)
    return levels


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "default_source": DEFAULT_SOURCE, "symbols": SYMBOLS}


@app.get("/levels/{symbol}", response_model=GammaLevels)
def levels(symbol: str, source: Optional[str] = Query(default=None)) -> GammaLevels:
    return _get_levels(symbol, source or DEFAULT_SOURCE)
