"""In-memory draft store for Meeting Context records.

Deliberately minimal: a process-local dict, not a database. Good enough for
driving the intake form end-to-end locally; swap for the real state store
(the DynamoDB-backed store in the architecture diagram) when this moves past
a single-process MVP slice.
"""

from __future__ import annotations

import uuid

from schemas import MeetingContextDraft, MeetingContextRecord

_DRAFTS: dict[str, MeetingContextRecord] = {}


def create_draft(draft: MeetingContextDraft) -> MeetingContextRecord:
    record = MeetingContextRecord(id=str(uuid.uuid4()), status="draft", **draft.model_dump())
    _DRAFTS[record.id] = record
    return record


def update_draft(draft_id: str, draft: MeetingContextDraft) -> MeetingContextRecord | None:
    if draft_id not in _DRAFTS:
        return None
    existing = _DRAFTS[draft_id]
    record = MeetingContextRecord(id=draft_id, status=existing.status, **draft.model_dump())
    _DRAFTS[draft_id] = record
    return record


def get_draft(draft_id: str) -> MeetingContextRecord | None:
    return _DRAFTS.get(draft_id)


def mark_confirmed(draft_id: str) -> MeetingContextRecord | None:
    record = _DRAFTS.get(draft_id)
    if record is None:
        return None
    record.status = "confirmed"
    return record


def _reset_for_tests() -> None:
    _DRAFTS.clear()
