"""Connection metadata for each chain source.

The admin "Connections hub" renders a form per source from these specs, and the
API builds a live source from saved credentials via :func:`build_source`. Keeping
the field metadata here (not in the adapters) means the UI can list every
provider without importing ``requests``/``websockets``.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldSpec:
    key: str                 # credential key (also the constructor kwarg)
    label: str
    env: str                 # env var fallback
    secret: bool = True      # mask in the UI / never echo back
    required: bool = True
    placeholder: str = ""


@dataclass(frozen=True)
class SourceSpec:
    name: str
    label: str
    kind: str                # "free" | "broker" | "vendor" | "local" | "offline"
    fields: list[FieldSpec] = field(default_factory=list)
    notes: str = ""

    @property
    def needs_credentials(self) -> bool:
        return bool(self.fields)


SOURCE_SPECS: dict[str, SourceSpec] = {
    "cboe": SourceSpec(
        "cboe", "Cboe (free, delayed)", "free",
        notes="No account or key. ~15-min delayed SPX/NDX+SPXW with gamma/IV/OI.",
    ),
    "tradier": SourceSpec(
        "tradier", "Tradier", "broker",
        [FieldSpec("token", "Access token", "TRADIER_TOKEN", placeholder="Bearer token")],
        notes="Greeks+OI via ORATS (end-of-day modeled). Free with a funded account.",
    ),
    "schwab": SourceSpec(
        "schwab", "Charles Schwab", "broker",
        [FieldSpec("token", "OAuth2 access token", "SCHWAB_ACCESS_TOKEN", placeholder="Bearer token (refresh every 7d)")],
        notes="Native greeks+IV+OI in one call. Requires an approved Schwab developer app.",
    ),
    "polygon": SourceSpec(
        "polygon", "Polygon.io", "vendor",
        [FieldSpec("api_key", "API key", "POLYGON_API_KEY")],
        notes="Real-time chain snapshot (I:SPX). Greeks/real-time need a paid Options plan.",
    ),
    "thetadata": SourceSpec(
        "thetadata", "ThetaData (local terminal)", "local",
        [FieldSpec("base_url", "Terminal URL", "THETADATA_URL", secret=False, required=False,
                   placeholder="http://127.0.0.1:25510")],
        notes="Runs against your local Theta Terminal gateway; it handles auth.",
    ),
    "tastytrade": SourceSpec(
        "tastytrade", "tastytrade (streaming)", "broker",
        [FieldSpec("username", "Username", "TASTYTRADE_USERNAME", secret=False),
         FieldSpec("password", "Password", "TASTYTRADE_PASSWORD")],
        notes="Greeks stream over DXLink. Free with a funded account. Experimental.",
    ),
    "sample": SourceSpec(
        "sample", "Sample fixtures (offline)", "offline",
        notes="Synthetic chains for demo/tests. Not market data.",
    ),
}


def build_source(name: str, credentials: dict | None = None):
    """Construct a ChainSource from saved credentials (env vars fill the gaps)."""
    creds = credentials or {}
    key = name.lower()
    if key == "sample":
        from .sample import SampleSource

        return SampleSource()
    if key == "cboe":
        from .cboe import CboeSource

        return CboeSource()
    if key == "tradier":
        from .tradier import TradierSource

        return TradierSource(token=creds.get("token") or None)
    if key == "schwab":
        from .schwab import SchwabSource

        return SchwabSource(token=creds.get("token") or None)
    if key == "polygon":
        from .polygon import PolygonSource

        return PolygonSource(api_key=creds.get("api_key") or None)
    if key == "thetadata":
        from .thetadata import ThetaDataSource

        return ThetaDataSource(base_url=creds.get("base_url") or None)
    if key == "tastytrade":
        from .tastytrade import TastytradeSource

        return TastytradeSource(username=creds.get("username") or None, password=creds.get("password") or None)
    raise ValueError(f"unknown source: {name!r}")
