"""The deck-build pipeline as one top-level LangGraph StateGraph — the
project's documented target architecture (see the old agent_definitions/
deck_planner_agent.py's "Multi-agent note": "existing architecture diagrams
for this project specify LangGraph as the overall pipeline orchestrator").

A node per pipeline step, same steps and same order builder.py always ran as
plain sequential function calls:

    1. fetch_facts        pipeline.data_analyst           fetch real data, record every value as a Fact
    2. generate_narrative pipeline.narrative_agent_runner  generate the 5 Commercial Intelligence Brief slides (REAL Brief Agent call)
    3. plan_deck          pipeline.deck_planner            decide structure (section/type/data-slice) -> DeckPlan
    4. write_spec         pipeline.spec_writer             turn the plan into a DeckSpec (every number a fact_id)
    5. validate           pipeline.validator               check the DeckSpec against the FactRegistry — BEFORE rendering
    6. render             pipeline.renderer                render the validated spec into real .pptx bytes
    7. post_render        pipeline.renderer                post_render_check — confirm the file matches the spec — AFTER rendering

Step 2 is the one real LLM/agent call anywhere in this graph — see
pipeline/narrative_agent_runner.py's docstring. Every other step is
deterministic, python-pptx only.

`validate` and `post_render` raise (DeckValidationError / DeckRenderError)
rather than writing an error into state — LangGraph just propagates a node's
exception out of `.invoke()` like any other function call, so builder.py's
existing fail-loudly contract carries over unchanged.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from pipeline.data_analyst import CustomerFacts, fetch_customer_facts
from pipeline.deck_planner import plan_deck
from pipeline.narrative_agent_runner import generate_narrative_slides
from pipeline.renderer import post_render_check, render_deck
from pipeline.spec_writer import write_deck_spec
from pipeline.validator import validate_deck_spec


class DeckValidationError(Exception):
    """The DeckSpec failed validation against its FactRegistry — nothing was rendered."""


class DeckRenderError(Exception):
    """The rendered file didn't match what the DeckSpec said it should contain."""


class DeckBuildState(TypedDict, total=False):
    customer: str
    meeting_date: str
    facts: CustomerFacts
    customer_fact_id: str
    meeting_date_fact_id: str
    narrative_slides: dict[str, Any]
    plan: Any
    deck_spec: Any
    pptx_bytes: bytes


def _fetch_facts(state: DeckBuildState) -> dict:
    facts = fetch_customer_facts(state["customer"])
    customer_fact_id = facts.registry.add(label="Customer", value=state["customer"], source_template="meeting_context")
    meeting_date_fact_id = facts.registry.add(
        label="Meeting date", value=state["meeting_date"], source_template="meeting_context"
    )
    return {"facts": facts, "customer_fact_id": customer_fact_id, "meeting_date_fact_id": meeting_date_fact_id}


def _generate_narrative(state: DeckBuildState) -> dict:
    # The one real agent call in this pipeline — generates against THIS
    # build's own `facts`/registry (never a separate fetch), so every
    # fact_id the agent cites is guaranteed valid below. See
    # pipeline/narrative_agent_runner.py's docstring for the full rationale.
    return {"narrative_slides": generate_narrative_slides(state["facts"])}


def _plan_deck(state: DeckBuildState) -> dict:
    return {"plan": plan_deck(state["facts"])}


def _write_spec(state: DeckBuildState) -> dict:
    deck_spec = write_deck_spec(
        state["plan"], state["facts"], state["customer_fact_id"], state["meeting_date_fact_id"], state["narrative_slides"]
    )
    return {"deck_spec": deck_spec}


def _validate(state: DeckBuildState) -> dict:
    errors = validate_deck_spec(state["deck_spec"], state["facts"].registry)
    if errors:
        raise DeckValidationError("; ".join(errors))
    return {}


def _render(state: DeckBuildState) -> dict:
    return {"pptx_bytes": render_deck(state["deck_spec"], state["facts"].registry)}


def _post_render(state: DeckBuildState) -> dict:
    issues = post_render_check(state["pptx_bytes"], state["deck_spec"], state["facts"].registry)
    if issues:
        raise DeckRenderError("; ".join(issues))
    return {}


def _build_deck_build_graph():
    graph = StateGraph(DeckBuildState)
    graph.add_node("fetch_facts", _fetch_facts)
    graph.add_node("generate_narrative", _generate_narrative)
    graph.add_node("plan_deck", _plan_deck)
    graph.add_node("write_spec", _write_spec)
    graph.add_node("validate", _validate)
    graph.add_node("render", _render)
    graph.add_node("post_render", _post_render)

    graph.add_edge(START, "fetch_facts")
    graph.add_edge("fetch_facts", "generate_narrative")
    graph.add_edge("generate_narrative", "plan_deck")
    graph.add_edge("plan_deck", "write_spec")
    graph.add_edge("write_spec", "validate")
    graph.add_edge("validate", "render")
    graph.add_edge("render", "post_render")
    graph.add_edge("post_render", END)
    return graph.compile()


deck_build_graph = _build_deck_build_graph()


def build_client_deck(customer: str, meeting_date: str) -> bytes:
    """Build the client-facing deck for one customer. Returns .pptx file bytes.

    Raises DeckValidationError if the spec references a fact that doesn't
    exist (blocks rendering entirely — nothing is built from an unverified
    spec), or DeckRenderError if the rendered file doesn't match the
    validated spec (a Renderer bug, not a data-trust problem — the
    Validator already cleared the data).
    """
    result = deck_build_graph.invoke({"customer": customer, "meeting_date": meeting_date})
    return result["pptx_bytes"]
