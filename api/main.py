"""FastAPI service: gamma levels API + a Connections admin hub.

The hub lets you save each provider's API credentials and test the connection
before using it; the levels endpoint then builds the active/selected source from
those saved credentials (env vars fill any gaps).

Security model — this is meant to bind to localhost for a single user:
  * CORS is locked to the dashboard origin(s) (``SPOTGAMMA_ALLOWED_ORIGINS``),
    never ``*`` — that's what stops a random site you visit from driving the
    credential-writing admin endpoints cross-origin.
  * If ``SPOTGAMMA_ADMIN_TOKEN`` is set, every ``/admin`` route requires a
    matching ``X-Admin-Token`` header (defense-in-depth for hosting it behind a
    trusted proxy; the browser never sees the token).

Run::

    uvicorn api.main:app --reload --port 8000   # binds 127.0.0.1 by default
    curl localhost:8000/levels/SPX
    open http://localhost:5173/admin            # via the dashboard
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from typing import Generic, TypeVar

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from spotgamma.history import TIMEFRAMES, fetch_history
from spotgamma.levels import compute_levels
from spotgamma.models import GammaLevels
from spotgamma.sources.specs import SOURCE_SPECS, build_source

from . import store

log = logging.getLogger("spotgamma.api")

DEFAULT_SOURCE = os.environ.get("SPOTGAMMA_SOURCE", "sample")
CACHE_TTL = float(os.environ.get("SPOTGAMMA_CACHE_TTL", "30"))
SYMBOLS = ["SPX", "NDX", "SPY", "QQQ"]
ADMIN_TOKEN = os.environ.get("SPOTGAMMA_ADMIN_TOKEN")

_V = TypeVar("_V")


class TTLCache(Generic[_V]):
    """Tiny thread-safe, size-bounded TTL cache.

    The API runs sync handlers in a threadpool, so the read-modify-write of a
    plain dict would race; this serializes access and evicts the oldest entry
    past ``maxsize`` so distinct symbol/source/timeframe keys can't grow forever.
    """

    def __init__(self, ttl: float, maxsize: int = 64) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._data: dict[tuple, tuple[float, _V]] = {}

    def get(self, key: tuple) -> _V | None:
        with self._lock:
            hit = self._data.get(key)
            if hit and (time.time() - hit[0]) < self._ttl:
                return hit[1]
            self._data.pop(key, None)
            return None

    def put(self, key: tuple, value: _V) -> None:
        with self._lock:
            if len(self._data) >= self._maxsize and key not in self._data:
                self._data.pop(next(iter(self._data)), None)  # evict oldest (insertion order)
            self._data[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


def _allowed_origins() -> list[str]:
    # Dashboard dev server + the Tauri desktop webview origins (macOS/Windows/Linux).
    raw = os.environ.get(
        "SPOTGAMMA_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,tauri://localhost,http://tauri.localhost,https://tauri.localhost",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="Spot Gamma API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "PUT", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)

_cache: TTLCache[GammaLevels] = TTLCache(CACHE_TTL)
# Price history is fetched far more often (per timeframe switch) and changes
# slowly; give it its own short cache so timeframe toggling stays snappy.
HISTORY_TTL = float(os.environ.get("SPOTGAMMA_HISTORY_TTL", "20"))
_history_cache: TTLCache[dict] = TTLCache(HISTORY_TTL)


def _resolved_source(requested: str | None) -> str:
    """Which source to use: explicit request > saved active > env default."""
    return requested or store.active_source() or DEFAULT_SOURCE


def _upstream_status(exc: Exception) -> int | None:
    """The HTTP status of an upstream vendor error, if the exception carries one."""
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None)


def _get_levels(symbol: str, source: str) -> GammaLevels:
    key = (symbol.upper(), source)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    try:
        chain = build_source(source, store.get_credentials(source)).get_chain(symbol)
        levels = compute_levels(chain)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        # Surface an unknown symbol as 404; everything else (network/auth/parse)
        # as 502 with the upstream status in the detail so clients can react.
        upstream = _upstream_status(e)
        code = 404 if upstream == 404 else 502
        detail = f"{source} source error: {e}" + (f" (upstream {upstream})" if upstream else "")
        log.warning("levels(%s, %s) failed: %s", symbol, source, e)
        raise HTTPException(status_code=code, detail=detail) from e
    _cache.put(key, levels)
    return levels


# --- Levels API -----------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "active_source": _resolved_source(None),
        "symbols": SYMBOLS,
        "timeframes": list(TIMEFRAMES),
    }


@app.get("/levels/{symbol}", response_model=GammaLevels)
def levels(symbol: str, source: str | None = Query(default=None)) -> GammaLevels:
    return _get_levels(symbol, _resolved_source(source))


@app.get("/history/{symbol}")
def history(symbol: str, tf: str = Query(default="5m")) -> dict:
    """OHLC bars for the trading chart (free Yahoo source, multi-timeframe)."""
    key = (symbol.upper(), tf)
    cached = _history_cache.get(key)
    if cached is not None:
        return cached
    try:
        data = fetch_history(symbol, tf)
    except Exception as e:  # network/parse error -> 502
        log.warning("history(%s, %s) failed: %s", symbol, tf, e)
        raise HTTPException(status_code=502, detail=f"history error: {e}") from e
    _history_cache.put(key, data)
    return data


# --- Connections hub ------------------------------------------------------
if not ADMIN_TOKEN:
    log.warning(
        "SPOTGAMMA_ADMIN_TOKEN is not set: /admin credential routes are UNAUTHENTICATED. "
        "Safe only when bound to localhost for a single user; set a token before exposing the API."
    )


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Gate /admin routes when SPOTGAMMA_ADMIN_TOKEN is configured."""
    if ADMIN_TOKEN and not (x_admin_token and secrets.compare_digest(x_admin_token, ADMIN_TOKEN)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin token required")


admin = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class CredentialsBody(BaseModel):
    credentials: dict[str, str] = {}


def _source_status(name: str) -> dict:
    spec = SOURCE_SPECS[name]
    saved = store.get_credentials(name)
    fields = []
    for f in spec.fields:
        env_set = bool(os.environ.get(f.env))
        fields.append(
            {
                "key": f.key,
                "label": f.label,
                "secret": f.secret,
                "required": f.required,
                "env": f.env,
                "placeholder": f.placeholder,
                # never echo secret values back; just whether they're set
                "saved": f.key in saved,
                "env_fallback": env_set,
                "value": (saved.get(f.key, "") if not f.secret else ""),
            }
        )
    needs = [f for f in spec.fields if f.required]
    configured = (not needs) or all(f.key in saved or os.environ.get(f.env) for f in needs)
    return {
        "name": spec.name,
        "label": spec.label,
        "kind": spec.kind,
        "notes": spec.notes,
        "needs_credentials": spec.needs_credentials,
        "fields": fields,
        "configured": configured,
        "active": _resolved_source(None) == spec.name,
    }


def _require_known(name: str) -> None:
    if name not in SOURCE_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown source {name!r}")


@admin.get("/sources")
def admin_sources() -> dict:
    return {"active": _resolved_source(None), "sources": [_source_status(n) for n in SOURCE_SPECS]}


@admin.put("/sources/{name}")
def admin_save(name: str, body: CredentialsBody) -> dict:
    _require_known(name)
    store.set_credentials(name, body.credentials)
    _cache.clear()  # credentials changed -> drop cached levels
    return _source_status(name)


@admin.post("/sources/{name}/test")
def admin_test(name: str, body: CredentialsBody | None = None) -> dict:
    _require_known(name)
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


@admin.put("/active/{name}")
def admin_set_active(name: str) -> dict:
    _require_known(name)
    store.set_active(name)
    _cache.clear()
    return {"active": name}


app.include_router(admin)
