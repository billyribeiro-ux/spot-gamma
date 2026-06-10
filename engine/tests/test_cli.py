"""CLI smoke + behavior tests via Typer's CliRunner.

All offline: the ``levels`` and ``export-thinkscript`` commands use the bundled
``sample`` source; ``market-structure`` has its network feeds stubbed. These
cover the CLI orchestration (arg parsing, stdout vs file output, exit codes)
that the library tests don't exercise.
"""

from __future__ import annotations

import json

from spotgamma.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_levels_to_stdout_is_valid_json():
    result = runner.invoke(app, ["levels", "SPX", "--source", "sample"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["symbol"] == "SPX"
    assert payload["spot"] > 0
    assert "call_wall" in payload and "net_gex" in payload


def test_levels_writes_file(tmp_path):
    out = tmp_path / "levels.json"
    result = runner.invoke(app, ["levels", "NDX", "--source", "sample", "--out", str(out)])
    assert result.exit_code == 0
    assert f"wrote {out}" in result.stdout
    payload = json.loads(out.read_text())
    assert payload["symbol"] == "NDX"


def test_levels_unknown_source_fails_cleanly():
    result = runner.invoke(app, ["levels", "SPX", "--source", "nope"])
    assert result.exit_code != 0  # surfaces the error, doesn't crash silently


def test_export_thinkscript_writes_study(tmp_path):
    out = tmp_path / "study.ts"
    result = runner.invoke(app, ["export-thinkscript", "SPY", "--source", "sample", "--out", str(out)])
    assert result.exit_code == 0
    script = out.read_text()
    # the Phase-4 study features must be present
    assert "input callWall" in script and "AddCloud" in script and "Alert(" in script


def test_market_structure_command(monkeypatch):
    # Stub the network feeds so the command is offline; sample source gives gamma.
    monkeypatch.setattr(
        "spotgamma.marketstructure.quotes.fetch_quote",
        lambda t: type("Q", (), {"price": {"^VIX": 15.0, "^VIX3M": 18.0, "^VVIX": 86.0, "DX-Y.NYB": 99.0}[t]})(),
    )
    monkeypatch.setattr(
        "spotgamma.marketstructure.fred.fetch_series",
        lambda sid: [type("P", (), {"value": {"BAMLH0A0HYM2": 2.7, "T10Y2Y": 0.5}[sid]})()],
    )
    monkeypatch.setattr(
        "spotgamma.marketstructure.feeds.fetch_constituent_closes",
        lambda *a, **k: {"AAA": [10.0] * 199 + [12.0]},
    )
    from spotgamma.marketstructure.gaps import Bar

    monkeypatch.setattr(
        "spotgamma.marketstructure.feeds.fetch_spy_bars",
        lambda *a, **k: [Bar(100, 101, 99, 100), Bar(100.2, 101, 99.8, 100.3)],
    )

    result = runner.invoke(app, ["market-structure", "SPX", "--source", "sample"])
    assert result.exit_code == 0
    assert "Market Structure" in result.stdout
    assert "RORO" in result.stdout and "regime score" in result.stdout
