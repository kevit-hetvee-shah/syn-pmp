"""Renderer: takes a *validated* DeckSpec + FactRegistry and produces the
real .pptx — the only stage that writes python-pptx content. Deterministic,
no LLM.

`render_deck()` builds the final slide sequence in exactly `deck_spec.slides`
order, so `post_render_check()` can zip the spec back against the rendered
file position-for-position — that's the "after" half of verification (the
Validator, in pipeline/validator.py, is the "before" half).
"""

from __future__ import annotations

import copy
import io
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData

from pipeline.models import CellSpec, ChartSpec, ChartValueSpec, DeckSpec, Fact, FactRegistry, SlideContentSpec
from utils.formatting import fmt_eur, fmt_pct_change, fmt_qty
from utils.pptx_clone import clone_slide, reorder_slides

# The RCR-reviewed template (23 slides, includes the Commercial Intelligence
# Brief section) — the live template as of 2026-10-30, superseding the older
# 16-slide "France_Template_Business_Review_Outlook_French .pptx". See
# pipeline/narrative_renderer.BRIEF_TEMPLATE_PATH (same file) for the
# narrative-slide-specific rendering this template's new section needs.
TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "France_Template_Business_Review_Outlook_French version_sent to RCR.pptx"
)


# ---------------------------------------------------------------------------
# Fact -> text resolution (shared by rendering and the post-render check)
# ---------------------------------------------------------------------------


def format_fact(fact: Fact) -> str:
    if isinstance(fact.value, str):
        return fact.value
    if fact.unit == "EUR":
        return fmt_eur(fact.value)
    return fmt_qty(fact.value, fact.unit)


def resolve_cell_text(cell: CellSpec, registry: FactRegistry) -> str | None:
    if cell.static_text is not None:
        return cell.static_text
    if cell.fact_id is not None:
        return format_fact(registry.get(cell.fact_id))
    if cell.pct_change_from is not None:
        prev_fact = registry.get(cell.pct_change_from[0])
        curr_fact = registry.get(cell.pct_change_from[1])
        return fmt_pct_change(float(prev_fact.value), float(curr_fact.value))
    return None  # not referenced by the spec — the template's own default stays untouched


def resolve_chart_value(value: ChartValueSpec, registry: FactRegistry) -> float:
    if value.fact_id is not None:
        return float(registry.get(value.fact_id).value)
    return sum(float(registry.get(fid).value) for fid in value.sum_of_fact_ids or [])


# ---------------------------------------------------------------------------
# python-pptx mechanics (cell/row writes that preserve template formatting)
# ---------------------------------------------------------------------------


def _table_shape(slide):
    return next(shape.table for shape in slide.shapes if shape.has_table)


def _chart_shape(slide):
    return next(shape.chart for shape in slide.shapes if shape.has_chart)


def _set_cell_text(table, row: int, col: int, text: str) -> None:
    """Edits the existing run's text in place instead of replacing it —
    `table.cell(r, c).text = text` resets bold/size/font/color to defaults.
    """
    cell = table.cell(row, col)
    paragraph = cell.text_frame.paragraphs[0]
    if paragraph.runs:
        paragraph.runs[0].text = text
        for extra_run in paragraph.runs[1:]:
            extra_run.text = ""
    else:
        cell.text = text


def _set_text_with_replacements(shape, replacements: dict[str, str]) -> None:
    for paragraph in shape.text_frame.paragraphs:
        full_text = "".join(run.text for run in paragraph.runs)
        if not full_text:
            continue
        for token, value in replacements.items():
            full_text = full_text.replace(token, value)
        if paragraph.runs:
            paragraph.runs[0].text = full_text
            for extra_run in paragraph.runs[1:]:
                extra_run.text = ""


def _remove_rows(table, row_indices: list[int]) -> None:
    rows = list(table.rows)
    for i in row_indices:
        table._tbl.remove(rows[i]._tr)


def _resize_data_rows(table, current_count: int, target_count: int, template_row_idx: int = 1, footer_tr=None) -> None:
    if target_count == current_count:
        return
    if target_count < current_count:
        rows = list(table.rows)
        for row in rows[1 + target_count : 1 + current_count]:
            table._tbl.remove(row._tr)
    else:
        template_tr = table.rows[template_row_idx]._tr
        for _ in range(target_count - current_count):
            new_tr = copy.deepcopy(template_tr)
            if footer_tr is not None:
                footer_tr.addprevious(new_tr)
            else:
                table._tbl.append(new_tr)


def _template_has_footer(slide_type: str) -> bool:
    """Whether the TEMPLATE slide this clones from physically has a trailing
    footer row (TOTAL) at all — true for both segment slide types regardless
    of whether THIS instance keeps it (see SlideContentSpec.keep_footer)."""
    return slide_type in ("segment_sales_page", "segment_share_page")


def _apply_row_resize(table, content: SlideContentSpec) -> None:
    if content.target_row_count is None:
        return

    if _template_has_footer(content.slide_type) and not content.keep_footer:
        # Drop the footer entirely first (e.g. a non-last segment page —
        # showing a partial "TOTAL" labeled row would be misleading).
        footer_row = table.rows[len(table.rows) - 1]
        table._tbl.remove(footer_row._tr)

    has_footer_now = _template_has_footer(content.slide_type) and content.keep_footer
    current_count = len(table.rows) - (2 if has_footer_now else 1)
    footer_tr = table.rows[len(table.rows) - 1]._tr if has_footer_now else None
    _resize_data_rows(table, current_count, content.target_row_count, template_row_idx=1, footer_tr=footer_tr)


def _apply_cells(table, cells: list[CellSpec], registry: FactRegistry) -> None:
    for cell in cells:
        text = resolve_cell_text(cell, registry)
        if text is not None:
            _set_cell_text(table, cell.row, cell.col, text)


def _apply_chart(slide, chart_spec: ChartSpec, registry: FactRegistry) -> None:
    chart = _chart_shape(slide)
    chart_data = CategoryChartData()
    chart_data.categories = [format_fact(registry.get(fid)) for fid in chart_spec.category_fact_ids]
    for series in chart_spec.series:
        chart_data.add_series(series.name, [resolve_chart_value(v, registry) for v in series.values])
    chart.replace_data(chart_data)


def _fill_slide(slide, content: SlideContentSpec, registry: FactRegistry, prs: Presentation) -> None:
    if content.slide_type == "static":
        return
    if content.slide_type == "narrative":
        # Deferred import: pipeline.narrative_renderer imports format_fact/
        # resolve_cell_text/resolve_chart_value FROM this module, so a
        # top-level import here would be circular. By the time this function
        # actually runs, both modules are already fully loaded.
        from pipeline.narrative_renderer import render_narrative_slide

        render_narrative_slide(slide, content.narrative_spec, registry, prs)
        return
    if content.slide_type == "cover":
        for shape in slide.shapes:
            if shape.has_text_frame and "[Client]" in shape.text_frame.text:
                resolved = {token: format_fact(registry.get(fid)) for token, fid in (content.text_replacements or {}).items()}
                _set_text_with_replacements(shape, resolved)
        return

    table = _table_shape(slide)
    # Row count must change BEFORE cell writes for pagination to land on the
    # right (post-resize) row indices — the Spec Writer always addresses
    # cells by their position in the FINAL row count, not the template's.
    _apply_row_resize(table, content)
    _apply_cells(table, content.cells, registry)
    if content.chart:
        _apply_chart(slide, content.chart, registry)


# ---------------------------------------------------------------------------
# Top-level render + post-render check
# ---------------------------------------------------------------------------


def render_deck(deck_spec: DeckSpec, registry: FactRegistry) -> bytes:
    """Produce the final .pptx bytes from a *validated* DeckSpec. Caller is
    responsible for having run pipeline.validator.validate_deck_spec first —
    this function doesn't re-check, it trusts its input.

    Two passes, deliberately: cloning must all happen first, *before* any
    filling — a clone made from `original_slides[src_idx]` after that slide
    has already been filled would clone the filled content (e.g. a second
    segment page would start from the first page's already-written rows
    instead of a pristine template row). Once every slide this deck needs
    exists (as either the original or a fresh clone of it), filling one
    can't affect any other.
    """
    prs = Presentation(str(TEMPLATE_PATH))
    original_slides = list(prs.slides)

    usage_count: dict[int, int] = {}
    target_slides = []
    for content in deck_spec.slides:
        src_idx = content.source_slide_index
        seen_before = usage_count.get(src_idx, 0)
        usage_count[src_idx] = seen_before + 1
        target_slides.append(original_slides[src_idx] if seen_before == 0 else clone_slide(prs, original_slides[src_idx]))

    for content, slide in zip(deck_spec.slides, target_slides):
        _fill_slide(slide, content, registry, prs)

    reorder_slides(prs, target_slides)
    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def post_render_check(pptx_bytes: bytes, deck_spec: DeckSpec, registry: FactRegistry) -> list[str]:
    """The "after" half of verification: re-open the rendered file and
    confirm what's actually in each cell matches what the DeckSpec + Fact
    Registry said should be there. Not a data-trust check (the Validator
    already did that) — a regression guard against Renderer bugs (this is
    exactly the class of bug shipped earlier: formatting loss, row-count
    mismatches — a mismatch here means the Renderer did something wrong, not
    that the data is untrustworthy).
    """
    issues: list[str] = []
    prs = Presentation(io.BytesIO(pptx_bytes))
    slides = list(prs.slides)
    if len(slides) != len(deck_spec.slides):
        issues.append(f"slide count mismatch: spec has {len(deck_spec.slides)}, rendered file has {len(slides)}")
        return issues

    for idx, (content, slide) in enumerate(zip(deck_spec.slides, slides)):
        label = f"slide {idx} ({content.slide_type})"
        if content.slide_type in ("static", "narrative"):
            # Narrative slides already went through validate_narrative_slide_spec
            # before rendering (the "before" half of verification), and
            # pipeline/narrative_renderer.py's own tests cover the Renderer-bug
            # class this check otherwise guards against (wrong shape/value for
            # a given block type) — not re-checked here to avoid duplicating
            # that per-block-type logic a second time.
            continue
        if content.slide_type == "cover":
            cover_text = "\n".join(s.text_frame.text for s in slide.shapes if s.has_text_frame)
            for token, fid in (content.text_replacements or {}).items():
                expected = format_fact(registry.get(fid))
                if expected not in cover_text:
                    issues.append(f"{label}: expected '{expected}' (from {token}) not found in rendered cover text")
            continue

        table = _table_shape(slide)
        if content.target_row_count is not None:
            has_footer_now = _template_has_footer(content.slide_type) and content.keep_footer
            actual_data_rows = len(table.rows) - (2 if has_footer_now else 1)
            if actual_data_rows != content.target_row_count:
                issues.append(
                    f"{label}: expected {content.target_row_count} data rows, rendered table has {actual_data_rows}"
                )
        for cell in content.cells:
            expected = resolve_cell_text(cell, registry)
            if expected is None:
                continue
            actual = table.cell(cell.row, cell.col).text
            if actual != expected:
                issues.append(f"{label}: cell ({cell.row},{cell.col}) expected '{expected}', rendered '{actual}'")
        if content.chart:
            chart = _chart_shape(slide)
            expected_categories = [format_fact(registry.get(fid)) for fid in content.chart.category_fact_ids]
            actual_categories = list(chart.plots[0].categories)
            if list(actual_categories) != expected_categories:
                issues.append(f"{label}: chart categories expected {expected_categories}, rendered {list(actual_categories)}")

    return issues
