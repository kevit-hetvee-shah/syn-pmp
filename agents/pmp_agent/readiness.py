"""Deterministic readiness check for the Meeting Context step.

IMPORTANT — scope boundary, deliberate:
This module only checks whether the 7 required fields are *present*. It does
NOT judge whether a hook is compelling, whether objectives are specific
enough, or anything else that needs actual language understanding. That
judgment belongs to the real Conversation Agent (the LLM-backed agent defined
in app.py, invoked through Portkey) — which is intentionally NOT wired up or
called anywhere in this module or in context_api.py, to avoid incurring any
Portkey/model cost while this intake-form slice is being built and tested.

`stub_followup_prompts()` below is the explicit extension point: swap its
body for a real call to the Conversation Agent once you're ready to spend
on inference. Until then it only returns rule-based "this field is empty"
prompts, never a semantic judgment.
"""

from __future__ import annotations

from schemas import MeetingContextDraft, REQUIRED_FIELDS, FieldReadiness, ReadinessResult

_FIELD_LABELS = {
    "customer_id": "Customer",
    "meeting_type": "Meeting type",
    "meeting_date": "Meeting date",
    "season": "Season",
    "campaign": "Campaign",
    "objectives": "Objectives",
}


def _is_filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def stub_followup_prompts(draft: MeetingContextDraft, missing_fields: list[str]) -> list[str]:
    """Rule-based-only placeholder for the Conversation Agent's follow-up
    questions. Deliberately does not call any LLM/agent/Portkey — see module
    docstring. Replace this function's body with a real agent call later.
    """
    return [f"{_FIELD_LABELS[field]} is required — please provide it." for field in missing_fields]


def check_readiness(draft: MeetingContextDraft) -> ReadinessResult:
    fields: list[FieldReadiness] = []
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        value = getattr(draft, field)
        ready = _is_filled(value)
        fields.append(FieldReadiness(field=field, ready=ready))
        if not ready:
            missing.append(field)

    ready_count = len(REQUIRED_FIELDS) - len(missing)
    return ReadinessResult(
        ready_count=ready_count,
        required_count=len(REQUIRED_FIELDS),
        all_ready=not missing,
        fields=fields,
        follow_up_prompts=stub_followup_prompts(draft, missing),
    )
