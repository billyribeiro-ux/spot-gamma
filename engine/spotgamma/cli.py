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


@app.command()
def backtest(
    horizon: int = typer.Option(5, help="Forward-return horizon in trading days (1, 5, 20…)."),
    bins: int = typer.Option(5, help="Quantile buckets for the calibration table."),
) -> None:
    """Out-of-sample backtest of the market-structure signals (§7 validation).

    Fetches the free historical panel (FRED + Yahoo), builds point-in-time
    features with forward SPY-return labels, and reports each signal's information
    coefficient, the composite, walk-forward OOS IC, and the score->return
    calibration. Sign convention: +1 = risk-off, so a POSITIVE IC is contrarian.
    """
    from .learning.backtest import (
        composite_report,
        prior_composite_fit_predict,
        signal_report,
        walk_forward,
        weighted_roro,
    )
    from .learning.calibration import calibrate
    from .learning.dataset import HISTORICAL_SIGNALS, build_dataset
    from .learning.panel import coverage, fetch_panel

    typer.echo(f"Fetching historical panel… (horizon {horizon}d)")
    panel = fetch_panel()
    ds = build_dataset(panel, horizons=(horizon,))
    cov = coverage(panel)
    typer.echo(f"  panel {panel[0].date}..{panel[-1].date}  ·  {len(ds)} labeled rows")
    typer.echo("  coverage: " + ", ".join(f"{k} n={cov[k]['n']}" for k in cov))
    typer.echo("")
    typer.echo("Information coefficient (Spearman) vs forward SPY return  [+ = contrarian, - = directional]")
    for k in HISTORICAL_SIGNALS:
        r = signal_report(ds, k, horizon)
        typer.echo(f"  {k:16s} IC {r.ic:+.3f}  n={r.n:5d}  terciles {[round(t, 4) for t in r.tercile_fwd]}")
    comp = composite_report(ds, horizon)
    typer.echo(
        f"  {'composite':16s} IC {comp.ic:+.3f}  n={comp.n:5d}  terciles {[round(t, 4) for t in comp.tercile_fwd]}"
    )
    wf = walk_forward(ds, horizon, prior_composite_fit_predict)
    typer.echo(f"\n  walk-forward OOS IC (prior composite): {wf.oos_ic:+.3f}  (n_oos={wf.n}, splits={wf.n_splits})")

    scores = [weighted_roro(r.scores) for r in ds if horizon in r.fwd_returns]
    rets = [r.fwd_returns[horizon] for r in ds if horizon in r.fwd_returns]
    calib = calibrate(scores, rets, horizon=horizon, n_bins=bins)
    typer.echo("\n  calibration (composite score bucket -> realized forward return):")
    for b in calib.buckets:
        lo = "-inf" if b.lo == float("-inf") else f"{b.lo:+.3f}"
        hi = "+inf" if b.hi == float("inf") else f"{b.hi:+.3f}"
        typer.echo(f"    [{lo}, {hi})  n={b.n:5d}  mean_fwd {b.mean_fwd:+.4f}  pos {b.pct_positive:.0%}")
    typer.echo("\nNote: a regime read describes state, not a return forecast; these are")
    typer.echo("measured, out-of-sample relationships, not a promise of accuracy.")


@app.command()
def learn(
    horizon: int = typer.Option(5, help="Forward-return horizon in trading days."),
    lam: float = typer.Option(0.5, help="Shrink-to-prior blend for calibrated weights (0=prior, 1=reliability)."),
    out: Path | None = typer.Option(None, help="Artifact path (default instance/learned_model.json)."),
) -> None:
    """Train + walk-forward-validate the learned model and persist the artifact.

    Calibrated weights are adopted only if they beat the documented prior
    out-of-sample; the contrarian return-tilt is adopted only if its OOS IC clears
    a modest floor. If neither helps, the live read keeps the prior — the artifact
    records the decision either way.
    """
    from .learning.dataset import build_dataset
    from .learning.model import train_model
    from .learning.panel import fetch_panel
    from .learning.store import save_model

    typer.echo(f"Fetching historical panel and training (horizon {horizon}d, lam {lam})…")
    ds = build_dataset(fetch_panel(), horizons=(horizon,))
    model = train_model(ds, horizon=horizon, lam=lam)
    v = model["validation"]
    typer.echo(f"  trained through {model['trained_through']} on {model['n_train']} rows")
    typer.echo(
        f"  OOS IC   prior {v['prior_oos_ic']:+.3f}   "
        f"calibrated {v['calibrated_oos_ic']:+.3f}   tilt {v['tilt_oos_ic']:+.3f}"
    )
    typer.echo(f"  adopt: weights={v['adopt_weights']}  tilt={v['adopt_tilt']}")
    path = save_model(model, str(out) if out else None)
    typer.echo(f"  wrote {path}")
    if not v["adopt_weights"] and not v["adopt_tilt"]:
        typer.echo("  → nothing beat the documented prior OOS; the live read keeps the §5 weights.")


@app.command("record-features")
def record_features(
    symbol: str = typer.Argument("SPX", help="Underlying to record the daily signal scores for."),
    source: str = typer.Option("cboe", help="Chain source for dealer gamma (cboe is free)."),
) -> None:
    """Append today's live signal scores to the daily feature log.

    Run this once per trading day (e.g. from cron) to accumulate a point-in-time
    history of EVERY signal — including breadth / put-call / dealer-gamma sign,
    which have no free back-history — so they can eventually be backtested
    (``log_to_dataset``). Gamma degrades gracefully: if the chain feed is down the
    macro/vol scores are still recorded, without the gamma vote.
    """
    from .learning.featurelog import gamma_sign_score, record_daily
    from .marketstructure.read import build_market_structure

    gx = spot = flip = None
    try:
        levels = _levels(symbol, source)
        gx, spot, flip = levels.net_gex, levels.spot, levels.zero_gamma
    except Exception as e:  # chain feed down -> record the macro/vol read anyway
        typer.echo(f"  (gamma unavailable: {e}; recording macro/vol only)")

    ms = build_market_structure(net_gex=gx, spot=spot, zero_gamma=flip)
    scores = {s.key: s.score for s in ms.read.signals}
    gsign = gamma_sign_score(gx, spot, flip)
    if gsign is not None:
        scores["gamma_sign"] = gsign

    log = record_daily(scores, spot, today=None)
    typer.echo(f"Recorded {symbol.upper()} for today — {len(scores)} signals, spot={spot}")
    typer.echo(f"  signals: {', '.join(f'{k} {v:+.2f}' for k, v in scores.items())}")
    typer.echo(f"  feature log now holds {len(log)} day(s); run `spotgamma learn` once it's deep enough.")


def main() -> None:  # console-script entry point
    app()


if __name__ == "__main__":
    main()
