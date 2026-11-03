"""Pydantic mirror of pipeline.models' narrative dataclasses — needed only at
the LangGraph `response_format=` boundary (structured output requires a
Pydantic BaseModel, not a plain dataclass). The dataclasses stay the single
source of truth everywhere else in the pipeline; this schema exists purely
to constrain and parse the Brief Agent's own output, then gets converted
once by pipeline/narrative_agent_runner.py.

Shared between agent_graphs/brief_agent.py (needs it at agent-build time, to
pass as `response_format`) and narrative_agent_runner.py (needs it to convert
the agent's structured_response back to the real dataclasses) — living here,
rather than in either of those modules, avoids a circular import between them.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


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
