"""Deck Builder — thin orchestrator. The actual work lives in pipeline/:

    1. pipeline.data_analyst           fetch real data, record every value as a Fact
    2. pipeline.narrative_agent_runner generate the 5 Commercial Intelligence Brief slides (REAL Brief Agent call)
    3. pipeline.deck_planner           decide structure (section/type/data-slice) -> DeckPlan
    4. pipeline.spec_writer            turn the plan into a DeckSpec (every number a fact_id)
    5. pipeline.validator              check the DeckSpec against the FactRegistry — BEFORE rendering
    6. pipeline.renderer               render the validated spec into real .pptx bytes
    7. pipeline.renderer               post_render_check — confirm the file matches the spec — AFTER rendering

Step 2 is the one real LLM/agent call anywhere in this module or the
pipeline it calls — see pipeline/narrative_agent_runner.py's docstring.
Every other step is deterministic, python-pptx only. `plan_deck` (step 3) is
the one remaining function designed to become a real call into
agent_definitions/deck_planner_agent.py later; nothing else here needs to
change when that happens.
"""

from __future__ import annotations

from pipeline.data_analyst import fetch_customer_facts
from pipeline.deck_planner import plan_deck
from pipeline.narrative_agent_runner import generate_narrative_slides
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

    # The one real agent call in this pipeline — generates against THIS
    # build's own `facts`/registry (never a separate fetch), so every
    # fact_id the agent cites is guaranteed valid below. See
    # pipeline/narrative_agent_runner.py's docstring for the full rationale.
    narrative_slides = generate_narrative_slides(facts)

    plan = plan_deck(facts)
    deck_spec = write_deck_spec(plan, facts, customer_fact_id, meeting_date_fact_id, narrative_slides)

    errors = validate_deck_spec(deck_spec, facts.registry)
    if errors:
        raise DeckValidationError("; ".join(errors))

    pptx_bytes = render_deck(deck_spec, facts.registry)

    issues = post_render_check(pptx_bytes, deck_spec, facts.registry)
    if issues:
        raise DeckRenderError("; ".join(issues))

    return pptx_bytes
