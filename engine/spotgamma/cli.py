"""Command-line interface for the spot-gamma engine.

Examples::

    spotgamma levels SPX --source sample --out levels.json
    spotgamma export-thinkscript SPX --source sample
"""

from __future__ import annotations

from pathlib import Path

import typer

from .export_thinkscript import render_thinkscript
from .levels import compute_levels
from .sources.base import get_source

app = typer.Typer(add_completion=False, help="Spot-gamma engine: chain -> dealer gamma levels.")

# Repo root: engine/spotgamma/cli.py -> parents[2]. Used to default the
# ThinkScript output to the tracked thinkscript/ directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _levels(symbol: str, source: str):
    return compute_levels(get_source(source).get_chain(symbol))


@app.command()
def levels(
    symbol: str = typer.Argument(..., help="Underlying, e.g. SPX, NDX, SPY, QQQ."),
    source: str = typer.Option("sample", help="Chain source: sample|cboe|tradier|schwab|polygon|thetadata|tastytrade."),
    out: Path | None = typer.Option(None, help="Write levels JSON here (else stdout)."),
) -> None:
    """Compute and print/save gamma levels for a symbol."""
    result = _levels(symbol, source)
    payload = result.model_dump_json(indent=2)
    if out:
        out.write_text(payload)
        typer.echo(f"wrote {out}")
    else:
        typer.echo(payload)


@app.command("export-thinkscript")
def export_thinkscript(
    symbol: str = typer.Argument(..., help="Underlying, e.g. SPX."),
    source: str = typer.Option("sample", help="Chain source: sample|cboe|tradier|schwab|polygon|thetadata|tastytrade."),
    out: Path | None = typer.Option(None, help="Output .ts path (default thinkscript/spot_gamma_<sym>.ts)."),
) -> None:
    """Render a Thinkorswim study with the computed levels as inputs."""
    result = _levels(symbol, source)
    script = render_thinkscript(result)
    target = out or _REPO_ROOT / "thinkscript" / f"spot_gamma_{symbol.lower()}.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(script)
    typer.echo(f"wrote {target}")


@app.command("market-structure")
def market_structure(
    symbol: str = typer.Argument("SPX", help="Underlying for the gamma gate, e.g. SPX."),
    source: str = typer.Option("cboe", help="Chain source for dealer gamma (cboe is free)."),
) -> None:
    """Print the composite market-structure regime read (vol + macro + gamma)."""
    from .marketstructure.read import build_market_structure

    levels = _levels(symbol, source)
    ms = build_market_structure(net_gex=levels.net_gex, spot=levels.spot, zero_gamma=levels.zero_gamma)
    r = ms.read
    typer.echo(f"Market Structure — {symbol.upper()}")
    typer.echo(f"  RORO {r.roro_score:+.2f} ({r.bias})  ·  vol {r.vol_regime}  ·  gamma gate x{r.gamma_modifier:.2f}")
    typer.echo(f"  regime score {r.regime_score:+.2f}" + ("  [DIVERGENCE]" if r.divergence else ""))
    for s in r.signals:
        typer.echo(f"    {s.score:+.2f}  {s.detail}")
    if ms.unavailable:
        typer.echo(f"  unavailable: {', '.join(ms.unavailable)}")


def main() -> None:  # console-script entry point
    app()


if __name__ == "__main__":
    main()
