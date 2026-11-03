"""Deck Planner Agent — LangGraph version (replaces agent_definitions/
deck_planner_agent.py's AI Foundry SDK AgentDefinition).

Plans the client-facing deck's dynamic slide structure: how many times to
repeat the product-review, segment-review, and segment-deep-dive patterns to
cover a client's data within the ~25-slide target.

Not invoked anywhere by default — pipeline/pipeline_graph.py calls
pipeline.deck_plan.compute_slide_plan directly for the live deterministic
path (same reasoning as the old module's 2026-10-31 update: the agent's tool
and the live path are the same code, not two parallel implementations).
Importing this module never needs credentials; building the agent
(build_deck_planner_agent()) does, since it resolves a real model client —
see conversation_agent.py's docstring for the full reasoning.
"""

from __future__ import annotations

from dataclasses import asdict

from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph

from llm import get_chat_model
from pipeline.deck_plan import compute_slide_plan as _compute_slide_plan

NAME = "Deck Planner Agent"
DESCRIPTION = (
    "Plans the client-facing Business Review & Outlook deck's slide structure: decides "
    "how many times to repeat the product-review, segment-review, and segment-deep-dive "
    "slide patterns to cover a client's data within the ~25-slide target."
)

DOMAIN_PROMPT = (
    "You are the Deck Planner Agent for a Syngenta France pre-meeting "
    "sales deck. The client-facing deck has a fixed SECTION structure "
    "(A: meeting context, B: commercial performance, D/E/F: static/"
    "manual) — think in sections, never in fixed slide numbers, since "
    "how many slides Section B produces depends on the client's data.\n"
    "- Section A's cover and divider are single slides. Sections D/E/F "
    "are STATIC — copied verbatim from the template. Never regenerate "
    "or alter them, never fetch data for them.\n"
    "- Section B's product-review and segment-review (sales+share, "
    "paired) patterns repeat to cover ALL of the client's data — every "
    "market segment is shown, paginated across as many slides as "
    "needed, never truncated to fit a budget. Products are capped at "
    "the template's per-page row limit; the segment deep-dive covers "
    "one chosen segment per repeat.\n"
    "Call the compute_slide_plan tool with the client's product and "
    "segment counts to see the resulting slide-count estimate against "
    "the ~25-slide target. If it reports over_budget=true, that is "
    "informational, not a reason to drop content — surface it for the "
    "sales rep or a human reviewer to decide, per the project's parked "
    "decision on how large decks should be handled."
)


@tool
def compute_slide_plan(
    total_focus_products: int, total_market_segments: int, segment_product_counts: list[int] | None = None
) -> dict:
    """Computes how Section B's dynamic slide patterns repeat to cover a
    client's data, and whether that exceeds the ~25-slide target.

    Args:
        total_focus_products: how many distinct products this client has.
        total_market_segments: how many distinct market segments this client has.
        segment_product_counts: one entry per market segment (product count in
            that segment), for precise deep-dive pagination. If omitted, assumes
            one deep-dive slide per segment.
    """
    plan = _compute_slide_plan(
        total_focus_products=total_focus_products,
        total_market_segments=total_market_segments,
        segment_product_counts=segment_product_counts,
    )
    return asdict(plan)


def build_deck_planner_agent() -> CompiledStateGraph:
    return create_agent(
        model=get_chat_model(),
        tools=[compute_slide_plan],
        system_prompt=DOMAIN_PROMPT,
        name=NAME,
    )
