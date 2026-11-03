"""REST API for the Meeting Context intake step (wizard step 1).

This router is intentionally self-contained: it imports only schemas,
mock_data, data_access, builder, readiness and storage — never
ai_foundry_platform_sdk, never a model client. Mounting it onto the AG-UI
app in app.py does not change what that app's existing /invocations route
does, and nothing in this file can trigger a Portkey call. Steps 2-4 of the
wizard (Customer view, Briefs, Recommendations) are out of scope — but the
confirmed Meeting Context can now generate a real .pptx directly (builder.py
— deterministic, no LLM), as a narrow stand-in for the full
Presentation/Approve steps.

Customer / season / product lists are DB-backed questions (per the user,
2026-10-30) — answered here via data_access.py, which currently runs the
sql_registry.py templates against the local dbx-data sample, not a live
Databricks connection. Every list response includes `data_source` so the
UI can show when it's looking at the (non-representative) local sample.
Meeting type stays static, per the user.
"""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter, HTTPException, Response

import builder
import data_access
import decks_mock_data
import mock_data
import storage
from distributor_profile import (
    KNOWN_DISTRIBUTOR_PROFILES,
    PARTNERSHIP_QUESTIONS,
    PRESSURE_QUESTIONS,
    MAX_DIMENSION_SCORE,
    resolve_draft_profile,
)
from readiness import check_readiness
from schemas import MeetingContextDraft, MeetingContextRecord, ReadinessResult

router = APIRouter(tags=["meeting-context"])


def _resolve_distributor_profile_or_422(draft: MeetingContextDraft) -> MeetingContextDraft:
    """Server-side source of truth for `draft.distributor_profile` — called
    on every save. Never trusts whatever profile value a client sent;
    recomputes/validates it from the known-profile pick or the dynamic
    section's scores instead. See distributor_profile.py's docstring.
    """
    resolved, errors = resolve_draft_profile(
        draft.distributor_profile_known, draft.distributor_profile, draft.pressure_scores, draft.partnership_scores
    )
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Invalid distributor profile answers.", "errors": errors})
    draft.distributor_profile = resolved
    return draft


def _resolve_location(draft: MeetingContextDraft) -> MeetingContextDraft:
    """Server-side source of truth for `draft.location` — called on every
    save, same reasoning as `_resolve_distributor_profile_or_422`: a
    read-only field is only actually read-only if the server enforces it,
    not just the UI. Always overwrites whatever a client sent with the
    customer account's real State (see data_access.get_customer_location's
    docstring — currently always None, no real source connected yet).
    """
    draft.location = data_access.get_customer_location(draft.customer_id) if draft.customer_id else None
    return draft


@router.get("/decks")
def list_previous_presentations() -> list[dict]:
    """Dashboard screen data. Static mock — see decks_mock_data.py docstring."""
    return decks_mock_data.PREVIOUS_PRESENTATIONS


@router.get("/customers")
def list_customers() -> dict:
    return {"data_source": data_access.current_data_source(), "items": data_access.get_distinct_customers()}


@router.get("/meeting-types", response_model=list[str])
def list_meeting_types() -> list[str]:
    return mock_data.MEETING_TYPES


@router.get("/seasons")
def list_seasons() -> dict:
    return {"data_source": data_access.current_data_source(), "items": data_access.get_distinct_seasons()}


@router.get("/campaigns")
def list_campaigns() -> dict:
    """Campaign (e.g. "F03") is a separate dimension from season — not the
    same list, see data_access.get_distinct_campaigns's docstring."""
    return {"data_source": data_access.current_data_source(), "items": data_access.get_distinct_campaigns()}


@router.get("/locations", response_model=list[str])
def list_locations() -> list[str]:
    return mock_data.LOCATIONS


@router.get("/regions", response_model=list[str])
def list_regions() -> list[str]:
    """Fixed, closed set the rep multi-selects from — see mock_data.REGIONS."""
    return mock_data.REGIONS


@router.get("/customer-location")
def get_customer_location(customer: str) -> dict:
    """Auto-fill source for the read-only Location field — see
    data_access.get_customer_location's docstring (always None today, no
    real State-on-Customer-Account source connected yet)."""
    return {"location": data_access.get_customer_location(customer)}


@router.get("/distributor-profiles", response_model=list[str])
def list_known_distributor_profiles() -> list[str]:
    return list(KNOWN_DISTRIBUTOR_PROFILES)


@router.get("/distributor-profile-questions")
def get_distributor_profile_questions() -> dict:
    """Scoring-question definitions for the dynamic assessment form —
    served from here (not hardcoded in the UI) so the questions/possible
    scores stay editable in one place, same reasoning as every other
    DB-backed dropdown in this API.
    """
    return {
        "pressure_to_protect_value": {
            "max_score": MAX_DIMENSION_SCORE,
            "questions": [dataclasses.asdict(q) for q in PRESSURE_QUESTIONS],
        },
        "partnership_mode": {
            "max_score": MAX_DIMENSION_SCORE,
            "questions": [dataclasses.asdict(q) for q in PARTNERSHIP_QUESTIONS],
        },
    }


@router.get("/product-suggestions")
def list_product_suggestions(customer: str | None = None) -> dict:
    return {
        "data_source": data_access.current_data_source(),
        "items": data_access.get_distinct_products(customer=customer),
    }


@router.post("/meeting-context/draft", response_model=MeetingContextRecord)
def save_draft(draft: MeetingContextDraft) -> MeetingContextRecord:
    draft = _resolve_distributor_profile_or_422(draft)
    draft = _resolve_location(draft)
    return storage.create_draft(draft)


@router.put("/meeting-context/{draft_id}/draft", response_model=MeetingContextRecord)
def update_draft(draft_id: str, draft: MeetingContextDraft) -> MeetingContextRecord:
    draft = _resolve_distributor_profile_or_422(draft)
    draft = _resolve_location(draft)
    record = storage.update_draft(draft_id, draft)
    if record is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return record


@router.get("/meeting-context/{draft_id}", response_model=MeetingContextRecord)
def get_draft(draft_id: str) -> MeetingContextRecord:
    record = storage.get_draft(draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return record


@router.get("/meeting-context/{draft_id}/readiness", response_model=ReadinessResult)
def get_readiness(draft_id: str) -> ReadinessResult:
    record = storage.get_draft(draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return check_readiness(record)


@router.post("/meeting-context/{draft_id}/confirm", response_model=MeetingContextRecord)
def confirm_draft(draft_id: str) -> MeetingContextRecord:
    """Confirm & Next. Blocks (422) unless all required fields are ready.

    Deliberately does not call the Conversation Agent here (see
    readiness.py) — this only enforces the deterministic required-field
    gate, matching the "N of N required fields ready" indicator in the UI.
    """
    record = storage.get_draft(draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    readiness = check_readiness(record)
    if not readiness.all_ready:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Required fields are missing.",
                "follow_up_prompts": readiness.follow_up_prompts,
            },
        )

    confirmed = storage.mark_confirmed(draft_id)
    assert confirmed is not None
    return confirmed


@router.get("/meeting-context/{draft_id}/deck")
def download_deck(draft_id: str) -> Response:
    """Generate and download the client-facing deck for a confirmed meeting
    context. Deterministic end to end (builder.py -> pipeline/*, python-pptx)
    — no LLM/agent call anywhere in the chain.

    Sections C/D/E/F stay static/gap-placeholder (no data source). Section B
    (KPI, products, market segments, one deep-dive) is real, fully paginated
    data from data_access.py (local sample unless Databricks is configured),
    verified both before rendering (every number traces to a fetched fact)
    and after (the rendered file is diffed against the spec that produced it).
    """
    record = storage.get_draft(draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if record.status != "confirmed":
        raise HTTPException(status_code=409, detail="Meeting context is not confirmed yet")
    if not record.customer_id or not record.meeting_date:
        raise HTTPException(status_code=422, detail="Missing customer or meeting date")

    try:
        pptx_bytes = builder.build_client_deck(record.customer_id, record.meeting_date)
    except builder.DeckValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Deck spec failed validation (not rendered): {exc}")
    except builder.DeckRenderError as exc:
        raise HTTPException(status_code=500, detail=f"Rendered file didn't match its spec: {exc}")

    filename = f"{record.customer_id}-business-review.pptx".replace(" ", "_")
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
