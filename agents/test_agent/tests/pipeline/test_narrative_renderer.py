"""Tests for pipeline/narrative_renderer.py. Builds NarrativeSlideSpec
instances by hand (standing in for what the Brief Agent would return — not
invoked anywhere in this codebase) and checks the resulting .pptx actually
contains the right shapes with the right values. No LLM/agent/Portkey call.
"""

import io

from pptx import Presentation
from pptx.enum.chart import XL_CHART_TYPE

from pipeline.data_analyst import fetch_customer_facts
from pipeline.models import (
    ChartSeriesSpec,
    ChartValueSpec,
    NarrativeCalloutBlock,
    NarrativeChartBlock,
    NarrativeKpiBlock,
    NarrativeSlideSpec,
)
from pipeline.narrative_facts import compute_narrative_facts
from pipeline.narrative_renderer import BRIEF_TEMPLATE_PATH, NARRATIVE_SLIDE_TEMPLATE_INDEX, render_narrative_deck
from pipeline.narrative_validator import validate_narrative_slide_spec
from pipeline.renderer import format_fact

_SEASON_FACT_EXCLUDE_KEYS = {
    "revenue_prev_fact_id",
    "revenue_curr_fact_id",
    "revenue_delta_fact_id",
    "best_season_revenue_fact_id",
}


def _executive_summary_spec(facts) -> NarrativeSlideSpec:
    narrative = compute_narrative_facts("executive_summary", facts)
    blocks = [
        NarrativeKpiBlock(
            label="Revenue",
            value_fact_id=narrative.facts["revenue_curr_fact_id"],
            delta_from_fact_id=narrative.facts["revenue_prev_fact_id"],
        ),
        NarrativeCalloutBlock(
            text="Account trajectory and recommendation go here.",
            cited_fact_ids=[narrative.facts["revenue_trajectory_fact_id"]],
        ),
    ]
    return NarrativeSlideSpec(slide_key="executive_summary", title="Executive Summary", blocks=blocks)


def _account_health_spec(facts) -> NarrativeSlideSpec:
    narrative = compute_narrative_facts("account_health", facts)
    season_fact_ids = [
        fid
        for key, fid in narrative.facts.items()
        if key.startswith("revenue_") and key.endswith("_fact_id") and key not in _SEASON_FACT_EXCLUDE_KEYS
    ]
    chart = NarrativeChartBlock(
        chart_type="line",
        title="Revenue by season",
        category_fact_ids=season_fact_ids,
        series=[ChartSeriesSpec(name="Revenue", values=[ChartValueSpec(fact_id=fid) for fid in season_fact_ids])],
    )
    return NarrativeSlideSpec(slide_key="account_health", title="Account Health & Value Realization", blocks=[chart])


def test_render_narrative_deck_produces_a_valid_pptx_with_real_shapes() -> None:
    facts = fetch_customer_facts("ACTURA")
    specs = [_executive_summary_spec(facts), _account_health_spec(facts)]
    for spec in specs:
        assert validate_narrative_slide_spec(spec, facts.registry) == []

    data = render_narrative_deck(specs, facts.registry)
    assert len(data) > 10_000

    prs = Presentation(io.BytesIO(data))
    slides = list(prs.slides)
    assert len(slides) == 2


def test_kpi_block_renders_the_real_formatted_value() -> None:
    facts = fetch_customer_facts("ACTURA")
    spec = _executive_summary_spec(facts)
    data = render_narrative_deck([spec], facts.registry)

    prs = Presentation(io.BytesIO(data))
    slide = list(prs.slides)[0]
    text_blocks = "\n".join(s.text_frame.text for s in slide.shapes if s.has_text_frame)

    kpi_block = spec.blocks[0]
    expected_value_fact = facts.registry.get(kpi_block.value_fact_id)
    assert format_fact(expected_value_fact) in text_blocks


def test_callout_block_renders_its_literal_text() -> None:
    facts = fetch_customer_facts("ACTURA")
    spec = _executive_summary_spec(facts)
    data = render_narrative_deck([spec], facts.registry)

    prs = Presentation(io.BytesIO(data))
    slide = list(prs.slides)[0]
    text_blocks = "\n".join(s.text_frame.text for s in slide.shapes if s.has_text_frame)
    assert "Account trajectory and recommendation go here." in text_blocks


def test_chart_block_renders_as_the_requested_chart_type_with_real_categories() -> None:
    facts = fetch_customer_facts("ACTURA")
    spec = _account_health_spec(facts)
    data = render_narrative_deck([spec], facts.registry)

    prs = Presentation(io.BytesIO(data))
    slide = list(prs.slides)[0]
    chart = next(s.chart for s in slide.shapes if s.has_chart)
    assert chart.chart_type == XL_CHART_TYPE.LINE

    chart_block = spec.blocks[0]
    expected_categories = [facts.registry.get(fid).value for fid in chart_block.category_fact_ids]
    actual_categories = list(chart.plots[0].categories)
    assert len(actual_categories) == len(expected_categories)


def test_original_title_is_preserved_from_the_template() -> None:
    facts = fetch_customer_facts("ACTURA")
    spec = _executive_summary_spec(facts)
    data = render_narrative_deck([spec], facts.registry)

    original = Presentation(str(BRIEF_TEMPLATE_PATH))
    original_slide = list(original.slides)[NARRATIVE_SLIDE_TEMPLATE_INDEX["executive_summary"]]
    original_title = next(
        s.text_frame.text for s in original_slide.shapes if s.has_text_frame and "Executive Summary" in s.text_frame.text
    )

    prs = Presentation(io.BytesIO(data))
    slide = list(prs.slides)[0]
    rendered_title = next(
        s.text_frame.text for s in slide.shapes if s.has_text_frame and "Executive Summary" in s.text_frame.text
    )
    assert rendered_title == original_title
