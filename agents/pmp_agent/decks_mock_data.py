"""Mock "previous presentations" list for the dashboard screen.

No deck-storage system exists yet (no Builder, no S3/SharePoint versions,
no Fact Registry) — these are static records matching the example content
in the "Pre-Meeting Agent 1.pdf" UI mockup (2026-10-30), so the dashboard
has something real to render. Replace with a real versions/state-store
query once the Builder and delivery pipeline exist.
"""

from __future__ import annotations

PREVIOUS_PRESENTATIONS: list[dict] = [
    {
        "customer": "Coopérative des Trois Rivières",
        "deck_type": "Business Review & Outlook",
        "date": "2026-11-12",
        "slide_count": 20,
        "status": "draft",
    },
    {
        "customer": "Agri Sud-Ouest Distribution",
        "deck_type": "Business Review & Outlook",
        "date": "2026-11-05",
        "slide_count": 11,
        "status": "data_changed",
    },
    {
        "customer": "Négoce Beauce Céréales",
        "deck_type": "Business Review & Outlook",
        "date": "2026-10-22",
        "slide_count": 10,
        "status": "approved",
    },
    {
        "customer": "Coop Plaine de Champagne",
        "deck_type": "Business Review & Outlook",
        "date": "2026-10-14",
        "slide_count": 9,
        "status": "approved",
    },
    {
        "customer": "Agri Val de Saône",
        "deck_type": "Business Review & Outlook",
        "date": "2026-10-02",
        "slide_count": 8,
        "status": "approved",
    },
    {
        "customer": "Union Agricole du Poitou",
        "deck_type": "Business Review & Outlook",
        "date": "2026-09-18",
        "slide_count": 10,
        "status": "approved",
    },
]
