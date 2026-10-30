"""Deck Builder — thin orchestrator. The actual work lives in pipeline/:

    1. pipeline.data_analyst   fetch real data, record every value as a Fact
    2. pipeline.deck_planner   decide structure (section/type/data-slice) -> DeckPlan
    3. pipeline.spec_writer    turn the plan into a DeckSpec (every number a fact_id)
    4. pipeline.validator      check the DeckSpec against the FactRegistry — BEFORE rendering
    5. pipeline.renderer       render the validated spec into real .pptx bytes
    6. pipeline.renderer       post_render_check — confirm the file matches the spec — AFTER rendering

No LLM/agent call anywhere in this module or the pipeline it calls — all
deterministic, python-pptx only. `plan_deck` (step 2) is the one function
designed to become a real call into agent_definitions/deck_planner_agent.py
later; nothing else here needs to change when that happens.
"""

from __future__ import annotations

from pipeline.data_analyst import fetch_customer_facts
from pipeline.deck_planner import plan_deck
from pipeline.renderer import post_render_check, render_deck
from pipeline.spec_writer import write_deck_spec
from pipeline.validator import validate_deck_spec


class DeckValidationError(Exception):
    """The DeckSpec failed validation against its FactRegistry — nothing was rendered."""


class DeckRenderError(Exception):
    """The rendered file didn't match what the DeckSpec said it should contain."""


def build_client_deck(customer: str, meeting_date: str) -> bytes:
    """Build the client-facing deck for one customer. Returns .pptx file bytes.

    Raises DeckValidationError if the spec references a fact that doesn't
    exist (blocks rendering entirely — nothing is built from an unverified
    spec), or DeckRenderError if the rendered file doesn't match the
    validated spec (a Renderer bug, not a data-trust problem — the
    Validator already cleared the data).
    """
    facts = fetch_customer_facts(customer)
    customer_fact_id = facts.registry.add(label="Customer", value=customer, source_template="meeting_context")
    meeting_date_fact_id = facts.registry.add(label="Meeting date", value=meeting_date, source_template="meeting_context")

    plan = plan_deck(facts)
    deck_spec = write_deck_spec(plan, facts, customer_fact_id, meeting_date_fact_id)

    errors = validate_deck_spec(deck_spec, facts.registry)
    if errors:
        raise DeckValidationError("; ".join(errors))

    pptx_bytes = render_deck(deck_spec, facts.registry)

    issues = post_render_check(pptx_bytes, deck_spec, facts.registry)
    if issues:
        raise DeckRenderError("; ".join(issues))

    return pptx_bytes
