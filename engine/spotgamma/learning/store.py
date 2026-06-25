"""Atomic JSON persistence for the learned model artifact.

Follows the same pattern as ``api/store.py`` / the put-call history: a temp file
plus ``os.replace`` for an atomic write, a tolerant read (missing/corrupt file
returns ``None``), and a default location under ``instance/`` (gitignored). The
artifact is produced by ``model.train_model`` and consumed by ``model.load`` /
the live read when present.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path


def default_model_path() -> Path:
    # engine/spotgamma/learning/store.py -> repo root / instance / learned_model.json
    return Path(__file__).resolve().parents[3] / "instance" / "learned_model.json"


def _resolve(path: str | None) -> Path:
    return Path(path) if path else Path(os.environ.get("SPOTGAMMA_MODEL") or default_model_path())


def save_model(model: dict, path: str | None = None) -> Path:
    """Atomically persist the model artifact; returns the path written."""
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".model-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(model, f, indent=2, sort_keys=True)
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return p


def load_model(path: str | None = None) -> dict | None:
    """Load the model artifact, or None if absent/corrupt (never raises)."""
    p = _resolve(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
