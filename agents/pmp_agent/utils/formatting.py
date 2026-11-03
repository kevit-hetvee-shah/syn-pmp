"""Shared number-formatting helpers for rendered slide content.

NOT_AVAILABLE is used wherever a percentage-change can't be computed (no
prior-period value to divide by) — distinct from the market-share gap
placeholder ("[%]"), which means "we have no data source for this at all."
"""

from __future__ import annotations

NOT_AVAILABLE = "N/D"  # "Non disponible"


def fmt_eur(value: float) -> str:
    return f"{value:,.0f} €".replace(",", " ")


def fmt_qty(value: float, unit: str) -> str:
    return f"{value:,.0f} {unit}".replace(",", " ")


def fmt_pct_change(previous: float, current: float) -> str:
    if not previous:
        return NOT_AVAILABLE
    return f"{(current - previous) / previous * 100:+.0f}%"
