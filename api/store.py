"""On-disk credential + active-source store for the admin hub.

Credentials entered in the Connections hub are saved here so the API can build
live sources from them. This is a **local, single-user admin tool**: secrets are
stored in a gitignored JSON file with 0600 permissions, not encrypted. Do not
expose this API to untrusted networks. Environment variables still work as a
fallback for anything not saved here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[1] / "instance" / "credentials.json"
_ACTIVE_KEY = "_active"


def _path() -> Path:
    return Path(os.environ.get("SPOTGAMMA_CONFIG", _DEFAULT))


def _read() -> dict:
    p = _path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass  # best-effort on platforms without POSIX perms


def get_credentials(name: str) -> dict:
    """Saved credentials for a source (empty dict if none)."""
    return dict(_read().get(name, {}))


def set_credentials(name: str, creds: dict) -> None:
    """Merge credentials for a source. An empty-string value clears that field."""
    data = _read()
    current = dict(data.get(name, {}))
    for k, v in creds.items():
        if v is None or v == "":
            current.pop(k, None)
        else:
            current[k] = v
    if current:
        data[name] = current
    else:
        data.pop(name, None)
    _write(data)


def configured_names() -> set[str]:
    return {k for k in _read() if k != _ACTIVE_KEY}


def active_source() -> str | None:
    return _read().get(_ACTIVE_KEY)


def set_active(name: str) -> None:
    data = _read()
    data[_ACTIVE_KEY] = name
    _write(data)
