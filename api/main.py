"""FastAPI service: gamma levels API + a Connections admin hub.

The hub lets you save each provider's API credentials and test the connection
before using it; the levels endpoint then builds the active/selected source from
those saved credentials (env vars fill any gaps).

Run::

    uvicorn api.main:app --reload --port 8000
    curl localhost:8000/levels/SPX
    open http://localhost:5173/admin   # via the dashboard
"""
from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from spotgamma.levels import compute_levels
from spotgamma.models import GammaLevels
from spotgamma.sources.specs import SOURCE_SPECS, build_source

from . import store

DEFAULT_SOURCE = os.environ.get("SPOTGAMMA_SOURCE", "sample")
CACHE_TTL = float(os.environ.get("SPOTGAMMA_CACHE_TTL", "30"))
SYMBOLS = ["SPX", "NDX", "SPY", "QQQ"]

app = FastAPI(title="Spot Gamma API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_cache: dict[tuple[str, str], tuple[float, GammaLevels]] = {}


def _resolved_source(requested: Optional[str]) -> str:
    """Which source to use: explicit request > saved active > env default."""
    return requested or store.active_source() or DEFAULT_SOURCE


def _get_levels(symbol: str, source: str) -> GammaLevels:
    key = (symbol.upper(), source)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        chain = build_source(source, store.get_credentials(source)).get_chain(symbol)
        levels = compute_levels(chain)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:  # source/network/validation/auth errors -> 502
        raise HTTPException(status_code=502, detail=f"{source} source error: {e}") from e
    _cache[key] = (now, levels)
    return levels


# --- Levels API -----------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "active_source": _resolved_source(None), "symbols": SYMBOLS}


@app.get("/levels/{symbol}", response_model=GammaLevels)
def levels(symbol: str, source: Optional[str] = Query(default=None)) -> GammaLevels:
    return _get_levels(symbol, _resolved_source(source))


# --- Connections hub ------------------------------------------------------
class CredentialsBody(BaseModel):
    credentials: dict[str, str] = {}


def _source_status(name: str) -> dict:
    spec = SOURCE_SPECS[name]
    saved = store.get_credentials(name)
    fields = []
    for f in spec.fields:
        env_set = bool(os.environ.get(f.env))
        fields.append({
            "key": f.key, "label": f.label, "secret": f.secret, "required": f.required,
            "env": f.env, "placeholder": f.placeholder,
            # never echo secret values back; just whether they're set
            "saved": f.key in saved,
            "env_fallback": env_set,
            "value": (saved.get(f.key, "") if not f.secret else ""),
        })
    needs = [f for f in spec.fields if f.required]
    configured = (not needs) or all(f.key in saved or os.environ.get(f.env) for f in needs)
    return {
        "name": spec.name, "label": spec.label, "kind": spec.kind, "notes": spec.notes,
        "needs_credentials": spec.needs_credentials, "fields": fields,
        "configured": configured, "active": _resolved_source(None) == spec.name,
    }


@app.get("/admin/sources")
def admin_sources() -> dict:
    return {"active": _resolved_source(None), "sources": [_source_status(n) for n in SOURCE_SPECS]}


@app.put("/admin/sources/{name}")
def admin_save(name: str, body: CredentialsBody) -> dict:
    if name not in SOURCE_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown source {name!r}")
    store.set_credentials(name, body.credentials)
    _cache.clear()  # credentials changed -> drop cached levels
    return _source_status(name)


@app.post("/admin/sources/{name}/test")
def admin_test(name: str, body: Optional[CredentialsBody] = None) -> dict:
    if name not in SOURCE_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown source {name!r}")
    # test against just-entered creds if provided, else what's saved
    creds = store.get_credentials(name)
    if body and body.credentials:
        creds = {**creds, **{k: v for k, v in body.credentials.items() if v}}
    started = time.time()
    try:
        ok, message = build_source(name, creds).test_connection()
    except Exception as e:  # construction failed (e.g. missing required cred)
        ok, message = False, str(e)
    return {"name": name, "ok": ok, "message": message, "latency_ms": round((time.time() - started) * 1000)}


@app.put("/admin/active/{name}")
def admin_set_active(name: str) -> dict:
    if name not in SOURCE_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown source {name!r}")
    store.set_active(name)
    _cache.clear()
    return {"active": name}
