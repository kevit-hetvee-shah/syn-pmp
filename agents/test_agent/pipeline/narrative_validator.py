"""Validator for NarrativeSlideSpec — the "before" half of verification for
the 5 "LLM Generated" slides, same role as validator.py plays for Section B:
mechanically confirm every value the Brief Agent chose to show resolves to a
real fact_id. It cannot (and doesn't try to) judge whether the agent's
CHOICE of chart type or layout is a good one, or whether callout prose
accurately reflects its cited facts — that's the Content Verifier Agent's
job, same division of labor as everywhere else in this pipeline.
"""

from __future__ import annotations

from pipeline.models import (
    ALLOWED_NARRATIVE_CHART_TYPES,
    FactRegistry,
    NarrativeCalloutBlock,
    NarrativeChartBlock,
    NarrativeKpiBlock,
    NarrativeSlideSpec,
    NarrativeTableBlock,
)


def validate_narrative_slide_spec(spec: NarrativeSlideSpec, registry: FactRegistry) -> list[str]:
    errors: list[str] = []
    label = f"narrative slide '{spec.slide_key}'"

    if not spec.blocks:
        errors.append(f"{label}: no blocks — slide would render empty")

    for block in spec.blocks:
        if isinstance(block, NarrativeChartBlock):
            errors += _validate_chart_block(label, block, registry)
        elif isinstance(block, NarrativeTableBlock):
            errors += _validate_table_block(label, block, registry)
        elif isinstance(block, NarrativeKpiBlock):
            errors += _validate_kpi_block(label, block, registry)
        elif isinstance(block, NarrativeCalloutBlock):
            errors += _validate_callout_block(label, block, registry)
        else:
            errors.append(f"{label}: unknown block type {type(block).__name__}")

    return errors


def _missing(label: str, fact_id: str, registry: FactRegistry) -> list[str]:
    return [] if fact_id in registry else [f"{label}: fact_id '{fact_id}' not found in registry"]


def _not_numeric(label: str, fact_id: str, registry: FactRegistry) -> list[str]:
    """Catches a real bug the first live Brief Agent call actually hit: a
    numeric slot (a chart value, a KPI's headline number, a %-change pair)
    pointed at a string-valued fact (e.g. a product name) — the renderer's
    `float(registry.get(fact_id).value)` crashes on that at render time, so
    this must be caught here, before rendering. Only call after `_missing`
    has already confirmed the fact_id exists.
    """
    value = registry.get(fact_id).value
    try:
        float(value)
    except (TypeError, ValueError):
        return [f"{label}: fact_id '{fact_id}' is not numeric (value={value!r}) — cannot be used here"]
    return []


def _validate_chart_block(label: str, block: NarrativeChartBlock, registry: FactRegistry) -> list[str]:
    errors: list[str] = []
    if block.chart_type not in ALLOWED_NARRATIVE_CHART_TYPES:
        errors.append(f"{label}: chart_type '{block.chart_type}' not in {ALLOWED_NARRATIVE_CHART_TYPES}")
    if not block.category_fact_ids:
        errors.append(f"{label}: chart block has no categories")
    for fid in block.category_fact_ids:
        errors += _missing(label, fid, registry)
    if not block.series:
        errors.append(f"{label}: chart block has no series")
    for series in block.series:
        if len(series.values) != len(block.category_fact_ids):
            errors.append(
                f"{label}: series '{series.name}' has {len(series.values)} values, "
                f"expected {len(block.category_fact_ids)} (one per category)"
            )
        for value in series.values:
            for fid in value.referenced_fact_ids():
                errors += _missing(label, fid, registry)
                if fid in registry:
                    errors += _not_numeric(label, fid, registry)
    return errors


def _validate_table_block(label: str, block: NarrativeTableBlock, registry: FactRegistry) -> list[str]:
    errors: list[str] = []
    if not block.headers:
        errors.append(f"{label}: table block has no headers")
    for row in block.rows:
        if len(row) != len(block.headers):
            errors.append(f"{label}: table row has {len(row)} cells, expected {len(block.headers)} (one per header)")
        for cell in row:
            if cell.fact_id is not None:
                errors += _missing(label, cell.fact_id, registry)
            if cell.pct_change_from is not None:
                for fid in cell.pct_change_from:
                    errors += _missing(label, fid, registry)
                    if fid in registry:
                        errors += _not_numeric(label, fid, registry)
    return errors


def _validate_kpi_block(label: str, block: NarrativeKpiBlock, registry: FactRegistry) -> list[str]:
    errors = _missing(label, block.value_fact_id, registry)
    if block.value_fact_id in registry:
        errors += _not_numeric(label, block.value_fact_id, registry)
    if block.delta_from_fact_id is not None:
        errors += _missing(label, block.delta_from_fact_id, registry)
        if block.delta_from_fact_id in registry:
            errors += _not_numeric(label, block.delta_from_fact_id, registry)
    return errors


def _validate_callout_block(label: str, block: NarrativeCalloutBlock, registry: FactRegistry) -> list[str]:
    errors: list[str] = []
    if not block.text.strip():
        errors.append(f"{label}: callout block has empty text")
    for fid in block.cited_fact_ids:
        errors += _missing(label, fid, registry)
    return errors
