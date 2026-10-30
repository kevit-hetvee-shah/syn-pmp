"""Pydantic schemas for the Meeting Context intake step (wizard step 1).

Pure data models — no agent/LLM/Portkey imports here on purpose, so this
module (and everything built on it in context_api.py) can be exercised and
tested without pulling in the AI Foundry SDK or incurring any model cost.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

REQUIRED_FIELDS = [
    "customer_id",
    "meeting_type",
    "meeting_date",
    "season",
    "campaign",
    "objectives",
]
# duration_minutes is deliberately NOT required (2026-10-30): it was
# originally gated because slide count used to be derived from meeting
# duration ("45 slides for 1hr meeting"). That relation no longer exists for
# this meeting type — pipeline/deck_plan.py's DEFAULT_TARGET_TOTAL_SLIDES is
# a fixed 25, not a function of duration — so there's nothing left for
# requiring this field to gate. Still captured as optional context.


class MeetingContextDraft(BaseModel):
    """Fields captured on the Meeting Context screen.

    Updated 2026-10-31 per the user: meeting_type is locked to a single
    fixed value for now (no other choice offered), season/campaign split
    into two separate selections (both DB-backed from the same distinct-
    seasons list), and hook moved from required to optional while
    season+campaign became required in its place. Location (replacing
    audience, 2026-10-30), hook, focus products and notes are optional
    context that sharpens the brief but doesn't block moving to step 2.

    Distributor Profile fields (added 2026-10-30, per the user's
    "Distributor Profiling" spec — see distributor_profile.py): entirely
    optional/skippable, never added to REQUIRED_FIELDS. `distributor_profile`
    is NEVER trusted as given by a client directly — context_api.py always
    recomputes/validates it via distributor_profile.resolve_draft_profile()
    on every save, so it is either the rep's directly-picked known profile,
    the dynamic section's computed classification, or None (not answered, or
    "cannot be determined" — in which case, per the spec, the dynamic
    section's answers are left out of the generated deck).
    """

    customer_id: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_date: Optional[str] = None  # ISO date, e.g. "2026-11-12"
    duration_minutes: Optional[int] = None
    season: Optional[str] = None
    campaign: Optional[str] = None
    location: Optional[str] = None
    objectives: Optional[str] = None
    hook: Optional[str] = None
    focus_products: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    distributor_profile_known: Optional[bool] = None
    distributor_profile: Optional[str] = None
    pressure_scores: dict[str, int] = Field(default_factory=dict)
    partnership_scores: dict[str, int] = Field(default_factory=dict)


class MeetingContextRecord(MeetingContextDraft):
    id: str
    status: str = "draft"  # "draft" | "confirmed"


class FieldReadiness(BaseModel):
    field: str
    ready: bool


class ReadinessResult(BaseModel):
    ready_count: int
    required_count: int
    all_ready: bool
    fields: list[FieldReadiness]
    # Deterministic, rule-based follow-up prompts only (e.g. "customer is
    # missing"). This is NOT the Conversation Agent's LLM-based clarifying
    # question logic — see readiness.py docstring for why that's stubbed out.
    follow_up_prompts: list[str]
