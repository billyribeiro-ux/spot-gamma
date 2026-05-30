"""Offline chain source backed by JSON fixtures.

This is the default source so the whole pipeline — engine, CLI, API, dashboard
— runs end-to-end with no API key or network. Fixtures live in
``engine/tests/fixtures/{symbol}_chain.json`` and follow the same schema the
live adapters normalize to.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import ChainSnapshot
from .base import ChainSource

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


class SampleSource(ChainSource):
    name = "sample"

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self.fixture_dir = fixture_dir or _FIXTURE_DIR

    def get_chain(self, symbol: str) -> ChainSnapshot:
        path = self.fixture_dir / f"{symbol.lower()}_chain.json"
        if not path.exists():
            available = ", ".join(sorted(p.stem.replace("_chain", "") for p in self.fixture_dir.glob("*_chain.json")))
            raise FileNotFoundError(f"no sample fixture for {symbol!r} at {path} (have: {available})")
        return ChainSnapshot.model_validate(json.loads(path.read_text()))
