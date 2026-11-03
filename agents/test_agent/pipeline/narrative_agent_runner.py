"""Real invocation of the Brief Agent — the ONLY code path in this whole
project that makes an actual Portkey/LLM call. Every other "agent" built in
this repo (Conversation, Deck Planner, Content Verifier, and the Brief Agent
itself before 2026-10-30) was deliberately never invoked, per the standing
rule that nothing in this codebase should trigger real cost/network traffic
without an explicit, deliberate decision to do so. That decision was made
for the Brief Agent specifically, because the Commercial Intelligence Brief
section's whole design point is a real agent choosing presentation per
slide — a hand-built stand-in (as every other agent in this repo still uses
for its tests) can't actually demonstrate that.

Set SKIP_NARRATIVE_AGENT=true to skip the real call (e.g. for a fast/free
manual smoke test of the rest of the pipeline) — the 5 slides render as a
plain "not yet generated" placeholder instead. The default (unset) is a real
call, matching what was explicitly asked for. Tests in this repo must NEVER
exercise the real-call path — see tests/conftest.py, which sets
SKIP_NARRATIVE_AGENT for the whole test session, and
tests/pipeline/test_narrative_agent_runner.py, which mocks build_agent
directly to test the Pydantic-to-dataclass conversion without that flag.
"""

from __future__ import annotations

import os
from typing import Annotated, Literal, Optional, Union

from ai_foundry_platform_sdk.app import build_agent
from pydantic import BaseModel, Field

from agent_definitions.brief_agent import build_brief_agent
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
from pipeline.narrative_validator import validate_narrative_slide_spec


class NarrativeAgentError(Exception):
    """The Brief Agent produced no structured output, or produced an
    invalid one (a fact_id it wasn't given, an empty slide, ...)."""


# ---------------------------------------------------------------------------
# Pydantic mirror of pipeline.models' narrative dataclasses — needed only at
# the structured_output_model boundary (Strands requires a Pydantic
# BaseModel there, not a plain dataclass). The dataclasses stay the single
# source of truth everywhere else in the pipeline; this schema exists purely
# to constrain and parse the agent's own output, then gets converted once.
# ---------------------------------------------------------------------------


class ChartValueSpecModel(BaseModel):
    fact_id: Optional[str] = None
    sum_of_fact_ids: Optional[list[str]] = None


class ChartSeriesSpecModel(BaseModel):
    name: str
    values: list[ChartValueSpecModel] = Field(default_factory=list)


class CellSpecModel(BaseModel):
    fact_id: Optional[str] = None
    static_text: Optional[str] = None
    pct_change_from: Optional[tuple[str, str]] = None


class NarrativeChartBlockModel(BaseModel):
    block_type: Literal["chart"] = "chart"
    chart_type: str
    title: str
    category_fact_ids: list[str] = Field(default_factory=list)
    series: list[ChartSeriesSpecModel] = Field(default_factory=list)


class NarrativeTableBlockModel(BaseModel):
    block_type: Literal["table"] = "table"
    headers: list[str]
    rows: list[list[CellSpecModel]] = Field(default_factory=list)


class NarrativeKpiBlockModel(BaseModel):
    block_type: Literal["kpi"] = "kpi"
    label: str
    value_fact_id: str
    delta_from_fact_id: Optional[str] = None


class NarrativeCalloutBlockModel(BaseModel):
    block_type: Literal["callout"] = "callout"
    text: str
    cited_fact_ids: list[str] = Field(default_factory=list)


NarrativeBlockModel = Annotated[
    Union[NarrativeChartBlockModel, NarrativeTableBlockModel, NarrativeKpiBlockModel, NarrativeCalloutBlockModel],
    Field(discriminator="block_type"),
]


class NarrativeSlideSpecModel(BaseModel):
    slide_key: str
    title: str
    blocks: list[NarrativeBlockModel] = Field(default_factory=list)


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
    AgentDefinition bound to `facts` (see agent_definitions.brief_agent's
    docstring for why a fresh binding per build matters), asks for exactly
    one slide, and converts+validates the structured result before
    returning. Raises NarrativeAgentError if the agent returns nothing
    usable or something invalid — the caller must not render an un-raised
    result.
    """
    definition = build_brief_agent(facts)
    prompt = (
        f"Generate the '{slide_key}' slide of the Commercial Intelligence Brief for {facts.customer}. "
        f"Call get_narrative_brief_inputs('{slide_key}') to get your inputs before deciding anything."
    )
    with build_agent(definition, session_id=f"{facts.customer}:{slide_key}") as managed:
        result = managed.agent(prompt, structured_output_model=NarrativeSlideSpecModel)

    if result.structured_output is None:
        raise NarrativeAgentError(f"Brief Agent returned no structured output for slide '{slide_key}'")

    spec = _spec_to_dataclass(result.structured_output)
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
