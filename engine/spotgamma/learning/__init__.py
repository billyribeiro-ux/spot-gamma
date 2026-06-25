"""Self-learning weight-calibration + backtest layer (the §7 open item).

``docs/MARKET_STRUCTURE.md`` §5 ships the composite weights as a *documented
prior, deliberately not fit to returns*, and §7 names the one unbuilt extension:

    "Calibrated weights / backtest — does the composite add information *over
     gamma alone*? The §5 weights remain a documented prior until this is run."

This package is that extension, built to the same honesty bar as the rest of the
engine:

* **Point-in-time correctness** (``panel.py``/``dataset.py``) — every feature on
  date *t* is computed from data observable at *t*; labels are *forward* returns
  (*t → t+h*). No bar is ever used before it exists. This is the single most
  important property; a backtest with lookahead is worse than none.
* **Out-of-sample discipline** (``backtest.py``) — walk-forward, expanding-window
  evaluation. Every reported number is from a block the model never trained on.
* **Shrink-to-prior learning** (``weights.py``) — learned weights are a *bounded
  adjustment* of the documented prior (ridge toward the prior + a convex blend),
  and are only adopted if they beat the prior out-of-sample. If learning doesn't
  help, the blend collapses to the prior. The prior stays the anchor.
* **Honest reporting** — information coefficient, hit rate, and calibration are
  reported with sample sizes and effective date windows; nothing claims to
  predict returns, only to *measure and adapt* how the documented signals relate
  to them.

Nothing here changes the live read unless learned weights are explicitly trained
and loaded; ``compose`` keeps using the documented prior by default.
"""

from __future__ import annotations
