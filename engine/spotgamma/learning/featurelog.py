"""Daily feature-log accumulator — the substrate that lets the learner compound.

The historical panel (``panel.py``) only covers the signals with clean *free
history* (vol + macro). Breadth, put/call, and the dealer-gamma sign have no
free back-history, so they cannot be backtested from a one-shot fetch. This module
fixes that the only honest way: by **recording the live, point-in-time signal
scores once per day** so that, over time, a genuine trainable history of *every*
signal accumulates.

Design (mirrors ``store.py`` / the put-call history):
* one JSON map ``{date: {"scores": {...}, "spot": float}}`` under ``instance/``
  (gitignored), deduped by date (last write of the day wins), atomic write;
* ``log_to_dataset`` turns the accumulated log into ``FeatureRow``s with **forward
  returns computed from the logged spot series** — so once enough days accrue, the
  backtest/IC machinery in ``backtest.py`` works on breadth/put-call/gamma too.

Point-in-time is automatic here: the scores were each computed live at the close
of their own day, and forward returns only ever look at *later* logged rows.
Pure functions everywhere except the tiny atomic read/write.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import date
from pathlib import Path

from .dataset import FeatureRow


def default_log_path() -> Path:
    # engine/spotgamma/learning/featurelog.py -> repo root / instance / feature_log.json
    return Path(__file__).resolve().parents[3] / "instance" / "feature_log.json"


def _resolve(path: str | None) -> Path:
    return Path(path) if path else Path(os.environ.get("SPOTGAMMA_FEATURE_LOG") or default_log_path())


def load_log(path: str | None = None) -> dict[str, dict]:
    """Load the daily feature log (``{date: {scores, spot}}``); {} if absent/corrupt."""
    p = _resolve(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def record_daily(
    scores: dict[str, float],
    spot: float | None,
    *,
    today: date | None = None,
    path: str | None = None,
) -> dict[str, dict]:
    """Append today's signal scores + spot to the log (atomic, deduped by date).

    Returns the full updated log. Re-recording on the same date overwrites that
    day's entry (last write wins), so an intraday re-run simply refreshes today.
    Only finite scores are stored; a missing ``spot`` is allowed (that day just
    won't anchor a forward return).
    """
    p = _resolve(path)
    day = (today or date.today()).isoformat()
    log = load_log(str(p))
    clean = {k: float(v) for k, v in scores.items() if isinstance(v, (int, float)) and v == v}
    entry: dict = {"scores": clean}
    if spot is not None and spot == spot:
        entry["spot"] = float(spot)
    log[day] = entry
    _atomic_write(p, log)
    return log


def _atomic_write(p: Path, log: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".featlog-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(log, f, indent=2, sort_keys=True)
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def log_to_dataset(
    log: dict[str, dict],
    horizons: tuple[int, ...] = (1, 5, 20),
) -> list[FeatureRow]:
    """Turn the daily log into point-in-time ``FeatureRow``s with forward returns.

    Forward return at horizon ``h`` is ``spot[i+h]/spot[i] - 1`` measured in
    **logged trading rows** (the log only contains days the read actually ran).
    A row is emitted when it has scores and at least one forward return; trailing
    rows with no matured horizon are dropped — exactly like ``dataset``.
    """
    days = sorted(log)
    spots = [log[d].get("spot") for d in days]
    rows: list[FeatureRow] = []
    for i, d in enumerate(days):
        scores = log[d].get("scores") or {}
        if not scores:
            continue
        s0 = spots[i]
        if not s0:
            continue
        fwd: dict[int, float] = {}
        for h in horizons:
            j = i + h
            if j < len(days) and spots[j]:
                fwd[h] = spots[j] / s0 - 1.0
        if not fwd:
            continue
        rows.append(FeatureRow(d, {k: float(v) for k, v in scores.items()}, fwd))
    return rows


def gamma_sign_score(net_gex: float | None, spot: float | None, zero_gamma: float | None) -> float | None:
    """The dealer-gamma directional vote as a recordable score (+1 risk-off / -1).

    Mirrors ``composite.compose``: negative regime (net GEX < 0, or spot below the
    flip) votes +1 (risk-off); otherwise -1. None when gamma is unavailable.
    """
    if net_gex is None or spot is None:
        return None
    negative_regime = net_gex < 0 or (zero_gamma is not None and spot < zero_gamma)
    return 1.0 if negative_regime else -1.0
