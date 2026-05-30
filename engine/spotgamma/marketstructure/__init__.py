"""Market-Structure intelligence (Phase 5).

Fuses the gamma engine's dealer-positioning read with cross-asset, volatility,
breadth, seasonality and event-risk signals into a single market-structure
picture. See ``docs/MARKET_STRUCTURE.md`` for the methodology — every threshold
and weight is documented there before it appears in code.

Layering (mirrors the rest of the engine):
- ``fred`` / ``quotes`` — free, no-key data fetchers with pure parsers.
- ``signals`` — normalize each raw input into a documented regime score.
- ``composite`` — combine signals into a transparent, inspectable read.
"""
