"""Validator: checks a DeckSpec against its FactRegistry *before* anything
is rendered. This is the "before" half of the verification the user asked
for — a failed check blocks rendering entirely, nothing gets built from an
unverified spec. (The Renderer's post-render check is the "after" half —
see pipeline/renderer.py.)
"""

from __future__ import annotations

from pipeline.models import CellSpec, DeckSpec, FactRegistry
from pipeline.narrative_validator import validate_narrative_slide_spec


def validate_deck_spec(deck_spec: DeckSpec, registry: FactRegistry) -> list[str]:
    errors: list[str] = []
    for slide_idx, slide in enumerate(deck_spec.slides):
        label = f"slide {slide_idx} ({slide.slide_type})"
        if slide.slide_type == "narrative":
            errors += validate_narrative_slide_spec(slide.narrative_spec, registry)
            continue
        for cell in slide.cells:
            errors += _check_cell(label, cell, registry)
        if slide.chart:
            for fid in slide.chart.category_fact_ids:
                if fid not in registry:
                    errors.append(f"{label}: chart category references unknown fact_id '{fid}'")
            for series in slide.chart.series:
                for value in series.values:
                    for fid in value.referenced_fact_ids():
                        if fid not in registry:
                            errors.append(f"{label}: chart series '{series.name}' references unknown fact_id '{fid}'")
        if slide.text_replacements:
            for token, fid in slide.text_replacements.items():
                if fid not in registry:
                    errors.append(f"{label}: text replacement '{token}' references unknown fact_id '{fid}'")
    return errors


def _check_cell(slide_label: str, cell: CellSpec, registry: FactRegistry) -> list[str]:
    errors: list[str] = []
    if not cell.is_data_driven() and cell.static_text is None:
        errors.append(f"{slide_label}: cell ({cell.row},{cell.col}) has no content — neither a fact_id nor static_text")
        return errors
    if cell.fact_id is not None and cell.fact_id not in registry:
        errors.append(f"{slide_label}: cell ({cell.row},{cell.col}) references unknown fact_id '{cell.fact_id}'")
    if cell.pct_change_from is not None:
        for fid in cell.pct_change_from:
            if fid not in registry:
                errors.append(f"{slide_label}: cell ({cell.row},{cell.col}) pct_change references unknown fact_id '{fid}'")
    return errors
