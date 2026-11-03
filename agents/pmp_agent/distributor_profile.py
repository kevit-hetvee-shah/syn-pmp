"""Distributor Profile scoring: classifies a customer into one of 4 static
profiles (Hedgehog, Wolf, Polar Bear, Dolphin) from the "Distributor
Profiling: Scoring Questions" spec (given by the user 2026-10-30).

Two ways to arrive at a profile, mirrored in MeetingContextDraft
(schemas.py):
  - KNOWN: the rep already knows it, picks directly from
    KNOWN_DISTRIBUTOR_PROFILES — no questions asked.
  - DYNAMIC: the rep doesn't know it, answers (any subset of — all are
    skippable) 10 scoring questions across 2 dimensions. Each dimension's
    total (max 60) places the customer in one quadrant of the 2x2 grid
    below. If too few questions are answered to classify (an unanswered
    dimension, or a total landing exactly on the 30-point boundary — the
    spec only defines ">30"/"<30", not "=30"), the profile is
    `None`/"cannot be determined" and, per the spec, the dynamic section's
    answers are NOT included in the generated deck.

Deliberately plain, deterministic, importable without the SDK — the
scoring/classification math is exactly the kind of thing that must never be
trusted from client-side JS alone (same reasoning as every other numeric
result in this project); context_api.py calls resolve_draft_profile() on
every draft save so the persisted `distributor_profile` is always
server-computed, never whatever a client happened to send.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

KNOWN_DISTRIBUTOR_PROFILES: tuple[str, ...] = ("Hedgehog", "Polar Bear", "Wolf", "Dolphin")

PROFILE_THRESHOLD = 30  # Value/Partnership > 30 is "high", < 30 is "low" — spec leaves exactly 30 undefined


@dataclasses.dataclass(frozen=True)
class ScoringQuestion:
    key: str
    criterion: str
    question: str
    possible_scores: list[int]


PRESSURE_QUESTIONS: list[ScoringQuestion] = [
    ScoringQuestion(
        key="portfolio",
        criterion="Portfolio",
        question=(
            "Are withdrawals / loss of authorisations affecting its revenue? "
            "Has it identified substitutes or replacement growth drivers?"
        ),
        possible_scores=[0, 2, 4, 6],
    ),
    ScoringQuestion(
        key="competition_profitability",
        criterion="Competition & profitability",
        question="Are its margins stable, or under pressure from generics, imports and purchasing groups?",
        possible_scores=[0, 6, 12, 18],
    ),
    ScoringQuestion(
        key="route_to_market",
        criterion="Route to market",
        question="Are its agreements being respected? Are channel deviations eroding its commercial terms?",
        possible_scores=[0, 4, 8, 12],
    ),
    ScoringQuestion(
        key="operations",
        criterion="Operations",
        question="Do availability, deliveries or regulatory dossiers put the campaign at risk?",
        possible_scores=[0, 2, 4, 6],
    ),
    ScoringQuestion(
        key="urgency",
        criterion="Urgency",
        question=(
            "Does it feel secure over the next 2-3 years, or see a risk of marginalisation within 12-18 months?"
        ),
        possible_scores=[0, 6, 12, 18],
    ),
]

PARTNERSHIP_QUESTIONS: list[ScoringQuestion] = [
    ScoringQuestion(
        key="teams",
        criterion="Teams",
        question="Does it allow only structured support, or would it welcome joint field visits / co-led activities?",
        possible_scores=[0, 2, 4, 6],
    ),
    ScoringQuestion(
        key="governance",
        criterion="Governance",
        question="Does it set objectives and timing internally, or build them with us?",
        possible_scores=[0, 6, 12, 18],
    ),
    ScoringQuestion(
        key="frameworks",
        criterion="Frameworks",
        question="Does it reject shared arrangements, or accept contracts, segmentation and shared rules?",
        possible_scores=[0, 6, 12, 18],
    ),
    ScoringQuestion(
        key="services",
        criterion="Services",
        question=(
            "Is its focus mainly price / product, or is it looking for joint services such as "
            "decision-support tools, data or marketing?"
        ),
        possible_scores=[0, 4, 8, 12],
    ),
    ScoringQuestion(
        key="ecosystem",
        criterion="Ecosystem",
        question="Does it prefer a local bilateral relationship, or value-chain / network projects involving data sharing?",
        possible_scores=[0, 2, 4, 6],
    ),
]

MAX_DIMENSION_SCORE = 60  # sum of each dimension's 5 max possible_scores


@dataclasses.dataclass
class DistributorProfileResult:
    pressure_total: Optional[int]
    partnership_total: Optional[int]
    profile: Optional[str]  # None = "cannot be determined" — keep the dynamic section out of the deck


def validate_scores(scores: dict[str, int], questions: list[ScoringQuestion]) -> list[str]:
    """Every key present must be a real question for this dimension, and its
    value one of that question's own possible_scores — partial/empty dicts
    are valid (skipping is allowed), this only rejects actively wrong input.
    """
    errors: list[str] = []
    by_key = {q.key: q for q in questions}
    for key, value in scores.items():
        question = by_key.get(key)
        if question is None:
            errors.append(f"unknown scoring question key '{key}'")
            continue
        if value not in question.possible_scores:
            errors.append(f"'{key}' score {value} is not one of {question.possible_scores}")
    return errors


def _dimension_total(scores: dict[str, int], questions: list[ScoringQuestion]) -> Optional[int]:
    valid_keys = {q.key for q in questions}
    answered = {k: v for k, v in scores.items() if k in valid_keys}
    if not answered:
        return None  # whole section skipped — "cannot be determined" territory
    return sum(answered.values())


def classify(pressure_total: Optional[int], partnership_total: Optional[int]) -> Optional[str]:
    if pressure_total is None or partnership_total is None:
        return None
    if pressure_total == PROFILE_THRESHOLD or partnership_total == PROFILE_THRESHOLD:
        return None  # the spec only defines >30/<30, not the exact boundary
    high_pressure = pressure_total > PROFILE_THRESHOLD
    high_partnership = partnership_total > PROFILE_THRESHOLD
    if high_pressure and not high_partnership:
        return "Hedgehog"
    if high_pressure and high_partnership:
        return "Wolf"
    if not high_pressure and not high_partnership:
        return "Polar Bear"
    return "Dolphin"


def compute_dynamic_profile(pressure_scores: dict[str, int], partnership_scores: dict[str, int]) -> DistributorProfileResult:
    pressure_total = _dimension_total(pressure_scores, PRESSURE_QUESTIONS)
    partnership_total = _dimension_total(partnership_scores, PARTNERSHIP_QUESTIONS)
    return DistributorProfileResult(
        pressure_total=pressure_total,
        partnership_total=partnership_total,
        profile=classify(pressure_total, partnership_total),
    )


def resolve_draft_profile(
    distributor_profile_known: Optional[bool],
    distributor_profile: Optional[str],
    pressure_scores: dict[str, int],
    partnership_scores: dict[str, int],
) -> tuple[Optional[str], list[str]]:
    """The single source of truth for what `MeetingContextDraft.distributor_profile`
    is actually allowed to be, given the rest of the distributor-profile fields.
    Called on every draft save (context_api.py) so the persisted value is always
    server-validated/computed — never whatever a client happened to send.

    Returns (resolved_profile, errors). `errors` non-empty means reject the
    save (422); `resolved_profile` is None either because nothing was
    answered yet or because the dynamic section couldn't be classified —
    both are valid, non-error states.
    """
    if distributor_profile_known is True:
        if distributor_profile is None:
            return None, []  # picked "I know it" but hasn't chosen one yet — in progress, not an error
        if distributor_profile not in KNOWN_DISTRIBUTOR_PROFILES:
            return None, [f"distributor_profile must be one of {list(KNOWN_DISTRIBUTOR_PROFILES)} when distributor_profile_known is true"]
        return distributor_profile, []

    if distributor_profile_known is False:
        errors = validate_scores(pressure_scores, PRESSURE_QUESTIONS) + validate_scores(partnership_scores, PARTNERSHIP_QUESTIONS)
        if errors:
            return None, errors
        return compute_dynamic_profile(pressure_scores, partnership_scores).profile, []

    return None, []  # distributor_profile_known is None — not answered yet, not an error
