"""Diagnostic (non-raising) variant of the deck pipeline.

builder.build_client_deck() raises on failure (right for an API endpoint —
fail loudly, don't ship a broken deck). This module runs the same pipeline
but reports what happened at each stage instead of raising, so an agent (or
a future "preview" API) can reason about the result — this is what
agent_definitions/content_verifier_agent.py's tool calls.
"""

from __future__ import annotations

from pipeline.data_analyst import fetch_customer_facts
from pipeline.deck_plan import compute_slide_plan
from pipeline.deck_planner import plan_deck
from pipeline.renderer import post_render_check, render_deck
from pipeline.spec_writer import write_deck_spec
from pipeline.validator import validate_deck_spec


def check_deck(customer: str, meeting_date: str) -> dict:
    """Run the full pipeline for one customer and report the outcome of
    every stage. validation_errors and post_render_issues should always be
    empty — a non-empty list here means a Renderer bug, not a data problem
    (the two checks exist for exactly that distinction).
    """
    facts = fetch_customer_facts(customer)
    customer_fid = facts.registry.add(label="Customer", value=customer, source_template="meeting_context")
    date_fid = facts.registry.add(label="Meeting date", value=meeting_date, source_template="meeting_context")

    budget = compute_slide_plan(total_focus_products=len(facts.products), total_market_segments=len(facts.segments))

    plan = plan_deck(facts)
    deck_spec = write_deck_spec(plan, facts, customer_fid, date_fid)
    validation_errors = validate_deck_spec(deck_spec, facts.registry)

    report = {
        "customer": customer,
        "fact_count": len(facts.registry),
        "product_count": len(facts.products),
        "segment_count": len(facts.segments),
        "planned_slide_count": len(plan.slides),
        "budget_target": budget.target_total_slides,
        "budget_over_target": budget.over_budget,
        "budget_overage": budget.overage,
        "budget_notes": budget.notes,
        "validation_errors": validation_errors,
        "rendered": False,
        "post_render_issues": [],
    }
    if validation_errors:
        return report

    pptx_bytes = render_deck(deck_spec, facts.registry)
    report["rendered"] = True
    report["rendered_slide_count"] = len(deck_spec.slides)
    report["post_render_issues"] = post_render_check(pptx_bytes, deck_spec, facts.registry)
    return report
