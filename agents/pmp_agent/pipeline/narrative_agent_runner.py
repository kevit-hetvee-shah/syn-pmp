"""Real invocation of the Brief Agent — the ONLY code path in this whole
project that makes an actual Portkey/LLM call. Every other agent built in
this repo (Conversation, Deck Planner, Content Verifier) is deliberately
never invoked, per the standing rule that nothing in this codebase should
trigger real cost/network traffic without an explicit, deliberate decision to
do so. That decision was made for the Brief Agent specifically, because the
Commercial Intelligence Brief section's whole design point is a real agent
choosing presentation per slide — a hand-built stand-in can't actually
demonstrate that.

Set SKIP_NARRATIVE_AGENT=true to skip the real call (e.g. for a fast/free
manual smoke test of the rest of the pipeline) — the 5 slides render as a
plain "not yet generated" placeholder instead. The default (unset) is a real
call, matching what was explicitly asked for. Tests in this repo must NEVER
exercise the real-call path — see tests/conftest.py, which sets
SKIP_NARRATIVE_AGENT for the whole test session, and
tests/pipeline/test_narrative_agent_runner.py, which mocks
agent_graphs.brief_agent.build_brief_agent directly to test the
Pydantic-to-dataclass conversion without that flag.
"""

from __future__ import annotations

import os

from agent_graphs.brief_agent import build_brief_agent
from pipeline.data_analyst import CustomerFacts
from pipeline.models import (
    CellSpec,
    ChartSeriesSpec,
    ChartValueSpec,
    NarrativeBlock,
    NarrativeCalloutBlock,
    NarrativeChartBlock,
    NarrativeKpiBlock,
    NarrativeSlideSpec,
    NarrativeTableBlock,
)
from pipeline.narrative_facts import NARRATIVE_SLIDE_KEYS
from pipeline.narrative_output_schema import (
    NarrativeCalloutBlockModel,
    NarrativeChartBlockModel,
    NarrativeKpiBlockModel,
    NarrativeSlideSpecModel,
    NarrativeTableBlockModel,
)
from pipeline.narrative_validator import validate_narrative_slide_spec


class NarrativeAgentError(Exception):
    """The Brief Agent produced no structured output, or produced an
    invalid one (a fact_id it wasn't given, an empty slide, ...)."""


def _block_to_dataclass(block_model) -> NarrativeBlock:
    if isinstance(block_model, NarrativeChartBlockModel):
        return NarrativeChartBlock(
            chart_type=block_model.chart_type,
            title=block_model.title,
            category_fact_ids=list(block_model.category_fact_ids),
            series=[
                ChartSeriesSpec(
                    name=series.name,
                    values=[ChartValueSpec(fact_id=v.fact_id, sum_of_fact_ids=v.sum_of_fact_ids) for v in series.values],
                )
                for series in block_model.series
            ],
        )
    if isinstance(block_model, NarrativeTableBlockModel):
        return NarrativeTableBlock(
            headers=list(block_model.headers),
            rows=[
                [
                    CellSpec(row=0, col=0, fact_id=cell.fact_id, static_text=cell.static_text, pct_change_from=cell.pct_change_from)
                    for cell in row
                ]
                for row in block_model.rows
            ],
        )
    if isinstance(block_model, NarrativeKpiBlockModel):
        return NarrativeKpiBlock(
            label=block_model.label, value_fact_id=block_model.value_fact_id, delta_from_fact_id=block_model.delta_from_fact_id
        )
    if isinstance(block_model, NarrativeCalloutBlockModel):
        return NarrativeCalloutBlock(text=block_model.text, cited_fact_ids=list(block_model.cited_fact_ids))
    raise NarrativeAgentError(f"unknown narrative block model type: {type(block_model).__name__}")


def _spec_to_dataclass(model: NarrativeSlideSpecModel) -> NarrativeSlideSpec:
    return NarrativeSlideSpec(slide_key=model.slide_key, title=model.title, blocks=[_block_to_dataclass(b) for b in model.blocks])


def _skipped_placeholder(slide_key: str) -> NarrativeSlideSpec:
    return NarrativeSlideSpec(
        slide_key=slide_key,
        title=slide_key.replace("_", " ").title(),
        blocks=[
            NarrativeCalloutBlock(
                text="Not yet generated — SKIP_NARRATIVE_AGENT is set for this build.", cited_fact_ids=[]
            )
        ],
    )


def invoke_brief_agent(facts: CustomerFacts, slide_key: str) -> NarrativeSlideSpec:
    """The one real Portkey/LLM call in this project. Builds a fresh
    compiled graph bound to `facts` (see agent_graphs.brief_agent's
    docstring for why a fresh binding per build matters), asks for exactly
    one slide, and converts+validates the structured result before
    returning. Raises NarrativeAgentError if the agent returns nothing
    usable or something invalid — the caller must not render an un-raised
    result.
    """
    graph = build_brief_agent(facts)
    prompt = (
        f"Generate the '{slide_key}' slide of the Commercial Intelligence Brief for {facts.customer}. "
        f"Call get_narrative_brief_inputs('{slide_key}') to get your inputs before deciding anything."
    )
    result = graph.invoke({"messages": [("user", prompt)]})

    structured = result.get("structured_response")
    if structured is None:
        raise NarrativeAgentError(f"Brief Agent returned no structured output for slide '{slide_key}'")
    if isinstance(structured, dict):
        structured = NarrativeSlideSpecModel.model_validate(structured)

    spec = _spec_to_dataclass(structured)
    errors = validate_narrative_slide_spec(spec, facts.registry)
    if errors:
        raise NarrativeAgentError(f"Brief Agent produced an invalid slide spec for '{slide_key}': {'; '.join(errors)}")
    return spec


def generate_narrative_slides(facts: CustomerFacts) -> dict[str, NarrativeSlideSpec]:
    """Generates all 5 Commercial Intelligence Brief slides for one deck
    build. Real agent calls by default; set SKIP_NARRATIVE_AGENT=true to
    render plain placeholders instead (never a fabricated stand-in)."""
    if os.environ.get("SKIP_NARRATIVE_AGENT", "").strip().lower() in ("1", "true", "yes"):
        return {slide_key: _skipped_placeholder(slide_key) for slide_key in NARRATIVE_SLIDE_KEYS}
    return {slide_key: invoke_brief_agent(facts, slide_key) for slide_key in NARRATIVE_SLIDE_KEYS}
