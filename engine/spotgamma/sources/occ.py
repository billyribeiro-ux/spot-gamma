"""Parse OCC-style option symbols.

Used by the Cboe and Polygon adapters, whose chains identify contracts by OCC
symbol (e.g. ``SPXW260618C00200000``): ROOT + YYMMDD + C/P + strike×1000 (8
digits). Parsing from the right is robust to variable-length roots.
"""
from __future__ import annotations

from datetime import date

from ..models import OptionType


def parse_occ_symbol(sym: str) -> tuple[str, date, OptionType, float]:
    """Return ``(root, expiration, option_type, strike)`` for an OCC symbol.

    ``sym`` may carry a vendor prefix like ``O:`` (Polygon); it is stripped.
    """
    s = sym.split(":", 1)[1] if ":" in sym else sym
    strike = int(s[-8:]) / 1000.0
    opt = OptionType.CALL if s[-9].upper() == "C" else OptionType.PUT
    yy, mm, dd = int(s[-15:-13]), int(s[-13:-11]), int(s[-11:-9])
    expiration = date(2000 + yy, mm, dd)
    root = s[:-15]
    return root, expiration, opt, strike
