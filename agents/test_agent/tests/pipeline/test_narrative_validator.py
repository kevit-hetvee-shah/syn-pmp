"""Tests for pipeline/narrative_validator.py — hand-built NarrativeSlideSpec
instances stand in for what the Brief Agent would eventually return (never
actually invoked — see agent_definitions/brief_agent.py).
"""

from pipeline.models import (
    CellSpec,
    ChartSeriesSpec,
    ChartValueSpec,
    FactRegistry,
    NarrativeCalloutBlock,
    NarrativeChartBlock,
    NarrativeKpiBlock,
    NarrativeSlideSpec,
    NarrativeTableBlock,
)
from pipeline.narrative_validator import validate_narrative_slide_spec


def _registry_with_facts() -> tuple[FactRegistry, str, str]:
    registry = FactRegistry()
    fid_a = registry.add(label="Revenue N-1", value=100.0, unit="EUR")
    fid_b = registry.add(label="Revenue N", value=120.0, unit="EUR")
    return registry, fid_a, fid_b


def test_valid_kpi_block_passes() -> None:
    registry, _, fid_b = _registry_with_facts()
    spec = NarrativeSlideSpec(
        slide_key="account_health",
        title="Account Health",
        blocks=[NarrativeKpiBlock(label="Revenue", value_fact_id=fid_b)],
    )
    assert validate_narrative_slide_spec(spec, registry) == []


def test_kpi_block_with_unknown_fact_id_is_rejected() -> None:
    registry, _, _ = _registry_with_facts()
    spec = NarrativeSlideSpec(
        slide_key="account_health",
        title="Account Health",
        blocks=[NarrativeKpiBlock(label="Revenue", value_fact_id="f999")],
    )
    errors = validate_narrative_slide_spec(spec, registry)
    assert len(errors) == 1
    assert "f999" in errors[0]


def test_empty_slide_is_rejected() -> None:
    registry, _, _ = _registry_with_facts()
    spec = NarrativeSlideSpec(slide_key="account_health", title="Account Health", blocks=[])
    errors = validate_narrative_slide_spec(spec, registry)
    assert any("no blocks" in e for e in errors)


def test_chart_block_series_length_mismatch_is_rejected() -> None:
    registry, fid_a, fid_b = _registry_with_facts()
    cat_fid = registry.add(label="Season", value="N-1")
    spec = NarrativeSlideSpec(
        slide_key="portfolio_shifts",
        title="Portfolio Shifts",
        blocks=[
            NarrativeChartBlock(
                chart_type="column",
                title="Revenue",
                category_fact_ids=[cat_fid],
                series=[ChartSeriesSpec(name="Revenue", values=[ChartValueSpec(fact_id=fid_a), ChartValueSpec(fact_id=fid_b)])],
            )
        ],
    )
    errors = validate_narrative_slide_spec(spec, registry)
    assert any("expected 1" in e for e in errors)


def test_chart_block_with_invalid_chart_type_is_rejected() -> None:
    registry, fid_a, _ = _registry_with_facts()
    cat_fid = registry.add(label="Season", value="N-1")
    spec = NarrativeSlideSpec(
        slide_key="portfolio_shifts",
        title="Portfolio Shifts",
        blocks=[
            NarrativeChartBlock(
                chart_type="waterfall",  # not in ALLOWED_NARRATIVE_CHART_TYPES
                title="Revenue",
                category_fact_ids=[cat_fid],
                series=[ChartSeriesSpec(name="Revenue", values=[ChartValueSpec(fact_id=fid_a)])],
            )
        ],
    )
    errors = validate_narrative_slide_spec(spec, registry)
    assert any("waterfall" in e for e in errors)


def test_valid_chart_block_passes() -> None:
    registry, fid_a, fid_b = _registry_with_facts()
    cat_a = registry.add(label="Season A", value="N-1")
    cat_b = registry.add(label="Season B", value="N")
    spec = NarrativeSlideSpec(
        slide_key="account_health",
        title="Account Health",
        blocks=[
            NarrativeChartBlock(
                chart_type="column",
                title="Revenue by season",
                category_fact_ids=[cat_a, cat_b],
                series=[ChartSeriesSpec(name="Revenue", values=[ChartValueSpec(fact_id=fid_a), ChartValueSpec(fact_id=fid_b)])],
            )
        ],
    )
    assert validate_narrative_slide_spec(spec, registry) == []


def test_table_block_row_width_mismatch_is_rejected() -> None:
    registry, fid_a, fid_b = _registry_with_facts()
    spec = NarrativeSlideSpec(
        slide_key="portfolio_shifts",
        title="Portfolio Shifts",
        blocks=[
            NarrativeTableBlock(
                headers=["Product", "Revenue"],
                rows=[[CellSpec(row=1, col=0, static_text="A"), CellSpec(row=1, col=1, fact_id=fid_a), CellSpec(row=1, col=2, fact_id=fid_b)]],
            )
        ],
    )
    errors = validate_narrative_slide_spec(spec, registry)
    assert any("expected 2" in e for e in errors)


def test_callout_block_with_unknown_cited_fact_is_rejected() -> None:
    registry, fid_a, _ = _registry_with_facts()
    spec = NarrativeSlideSpec(
        slide_key="executive_summary",
        title="Executive Summary",
        blocks=[NarrativeCalloutBlock(text="Revenue grew.", cited_fact_ids=[fid_a, "f999"])],
    )
    errors = validate_narrative_slide_spec(spec, registry)
    assert any("f999" in e for e in errors)


def test_callout_block_with_empty_text_is_rejected() -> None:
    registry, fid_a, _ = _registry_with_facts()
    spec = NarrativeSlideSpec(
        slide_key="executive_summary",
        title="Executive Summary",
        blocks=[NarrativeCalloutBlock(text="   ", cited_fact_ids=[fid_a])],
    )
    errors = validate_narrative_slide_spec(spec, registry)
    assert any("empty text" in e for e in errors)
