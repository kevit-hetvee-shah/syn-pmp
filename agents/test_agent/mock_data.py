"""Static reference data for the Meeting Context step.

As of 2026-10-30, customers / seasons / focus-product suggestions are no
longer mock lists here — the user confirmed that data, and moved it to
data_access.py (backed by sql_registry.py's templates, executed locally
against the dbx-data sample until a real Databricks MCP tool exists). Only
genuinely static things remain here: meeting type and location ("could be
static for now", per the user) — neither has a data-source question
attached yet.

REGIONS (added 2026-11-02, "Set the Region" story) is a fixed, closed set —
not a data-source question either: it's the sales-territory breakdown the
rep picks from (distinct from LOCATIONS, which is the detailed French
administrative region and is no longer user-selected — see
data_access.get_customer_location's docstring for why Location is read-only
now instead).
"""

from __future__ import annotations

_CURRENT_USER = "hetvee.shah@botprosolutions.com"


def current_user() -> str:
    """Stand-in for a real auth session. Always returns the same mock rep."""
    return _CURRENT_USER


# Locked to a single value, per the user (2026-10-31): "No other options
# could be selected for now." The other brief types from Epic 4 (negotiation
# brief, in-season brief, etc.) aren't supported yet — only one template
# (France Business Review & Outlook) is confirmed/built.
MEETING_TYPES: list[str] = [
    "Business Review & Outlook",
]

LOCATIONS: list[str] = [
    "Hauts-de-France",
    "Grand Est",
    "Normandie",
    "Île-de-France",
    "Centre-Val de Loire",
    "Bourgogne-Franche-Comté",
    "Pays de la Loire",
    "Bretagne",
    "Nouvelle-Aquitaine",
    "Occitanie",
    "Auvergne-Rhône-Alpes",
    "Provence-Alpes-Côte d'Azur",
]

# Exactly these five, per the "Set the Region" story — a multi-select, not a
# single pick (a rep's territory can span more than one).
REGIONS: list[str] = [
    "EST",
    "NORD",
    "OUEST",
    "SUD EST",
    "SUD OUEST",
]
