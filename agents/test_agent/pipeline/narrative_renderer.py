"""Renderer for the 5 "LLM Generated" narrative slides (Commercial
Intelligence Brief). Deliberately separate from pipeline/renderer.py: that
renderer fills a FIXED shape per template slide (one table, maybe one
chart); this one builds a variable STACK of fresh shapes from whatever
blocks a NarrativeSlideSpec contains, stacked vertically in the content area
below the slide's title. Still deterministic, still no LLM — the blocks are
either hand-built (tests) or produced by the Brief Agent (not invoked in
this codebase; see agent_definitions/brief_agent.py), never free-formed by
this module.

Uses a SEPARATE template file from pipeline/renderer.py's TEMPLATE_PATH —
only the newer "...sent to RCR.pptx" template has these 5 slides at all (the
older 16-slide template has no Commercial Intelligence Brief section).
Merging this standalone Brief sub-deck into the main client deck is a
follow-up integration step, not done here — see this module's own
docstring note at BRIEF_TEMPLATE_PATH.
"""

from __future__ import annotations

import io
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from pipeline.models import (
    FactRegistry,
    NarrativeCalloutBlock,
    NarrativeChartBlock,
    NarrativeKpiBlock,
    NarrativeSlideSpec,
    NarrativeTableBlock,
)
from pipeline.renderer import format_fact, resolve_cell_text, resolve_chart_value
from utils.formatting import fmt_pct_change
from utils.pptx_clone import clone_slide, reorder_slides

# The RCR-reviewed template — the only one with a Commercial Intelligence
# Brief section. pipeline/renderer.TEMPLATE_PATH stays pointed at the older
# 16-slide template until the two are deliberately merged.
BRIEF_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "France_Template_Business_Review_Outlook_French version_sent to RCR.pptx"
)

# 0-indexed position of each narrative slide in BRIEF_TEMPLATE_PATH — gives
# us the title/footer/"LLM Generated" tag shapes to clone, already styled.
NARRATIVE_SLIDE_TEMPLATE_INDEX = {
    "executive_summary": 2,
    "account_health": 3,
    "portfolio_shifts": 4,
    "market_benchmarking": 5,
    "operational_risk": 6,
}

_CHART_TYPE_MAP = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
    "area": XL_CHART_TYPE.AREA,
}

_CONTENT_LEFT = Inches(0.6)
_CONTENT_TOP_START = Inches(1.6)  # below the template's title placeholder
_BLOCK_GAP = Inches(0.25)
_CHART_HEIGHT = Inches(3.0)
_KPI_HEIGHT = Inches(0.9)
_CALLOUT_HEIGHT = Inches(0.9)
_TABLE_ROW_HEIGHT = Inches(0.4)


def _content_width(prs: Presentation) -> int:
    return prs.slide_width - 2 * _CONTENT_LEFT


def _block_height(block) -> int:
    if isinstance(block, NarrativeChartBlock):
        return _CHART_HEIGHT
    if isinstance(block, NarrativeKpiBlock):
        return _KPI_HEIGHT
    if isinstance(block, NarrativeCalloutBlock):
        return _CALLOUT_HEIGHT
    if isinstance(block, NarrativeTableBlock):
        return _TABLE_ROW_HEIGHT * (1 + len(block.rows))
    raise TypeError(f"unknown narrative block type: {type(block).__name__}")


def _add_chart_block(slide, block: NarrativeChartBlock, registry: FactRegistry, left, top, width, height) -> None:
    chart_data = CategoryChartData()
    chart_data.categories = [format_fact(registry.get(fid)) for fid in block.category_fact_ids]
    for series in block.series:
        chart_data.add_series(series.name, [resolve_chart_value(v, registry) for v in series.values])
    graphic_frame = slide.shapes.add_chart(_CHART_TYPE_MAP[block.chart_type], left, top, width, height, chart_data)
    chart = graphic_frame.chart
    chart.has_title = True
    chart.chart_title.text_frame.text = block.title


def _add_table_block(slide, block: NarrativeTableBlock, registry: FactRegistry, left, top, width, height) -> None:
    n_rows = 1 + len(block.rows)
    n_cols = len(block.headers)
    table = slide.shapes.add_table(n_rows, n_cols, left, top, width, height).table
    for col, heading in enumerate(block.headers):
        cell = table.cell(0, col)
        cell.text = heading
        runs = cell.text_frame.paragraphs[0].runs
        if runs:
            runs[0].font.bold = True
    for row_idx, row in enumerate(block.rows, start=1):
        for col_idx, cell_spec in enumerate(row):
            text = resolve_cell_text(cell_spec, registry)
            if text is not None:
                table.cell(row_idx, col_idx).text = text


def _add_kpi_block(slide, block: NarrativeKpiBlock, registry: FactRegistry, left, top, width, height) -> None:
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    label_p = tf.paragraphs[0]
    label_p.text = block.label
    label_p.runs[0].font.size = Pt(12)

    value_p = tf.add_paragraph()
    value_text = format_fact(registry.get(block.value_fact_id))
    if block.delta_from_fact_id is not None:
        prev = float(registry.get(block.delta_from_fact_id).value)
        curr = float(registry.get(block.value_fact_id).value)
        value_text = f"{value_text}  ({fmt_pct_change(prev, curr)})"
    value_p.text = value_text
    value_p.runs[0].font.size = Pt(20)
    value_p.runs[0].font.bold = True


def _add_callout_block(slide, block: NarrativeCalloutBlock, registry: FactRegistry, left, top, width, height) -> None:
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.paragraphs[0].text = block.text
    tf.paragraphs[0].alignment = PP_ALIGN.LEFT


def render_narrative_slide(slide, spec: NarrativeSlideSpec, registry: FactRegistry, prs: Presentation) -> None:
    """Fills a cloned base slide (title/footer/"LLM Generated" tag already
    present) with `spec.blocks`, stacked top to bottom. Caller is
    responsible for having run validate_narrative_slide_spec first.
    """
    content_width = _content_width(prs)
    top = _CONTENT_TOP_START
    for block in spec.blocks:
        height = _block_height(block)
        if isinstance(block, NarrativeChartBlock):
            _add_chart_block(slide, block, registry, _CONTENT_LEFT, top, content_width, height)
        elif isinstance(block, NarrativeTableBlock):
            _add_table_block(slide, block, registry, _CONTENT_LEFT, top, content_width, height)
        elif isinstance(block, NarrativeKpiBlock):
            _add_kpi_block(slide, block, registry, _CONTENT_LEFT, top, content_width, height)
        elif isinstance(block, NarrativeCalloutBlock):
            _add_callout_block(slide, block, registry, _CONTENT_LEFT, top, content_width, height)
        top += height + _BLOCK_GAP


def render_narrative_deck(specs: list[NarrativeSlideSpec], registry: FactRegistry) -> bytes:
    """Standalone preview deck: just the narrative slides this call was
    given, in order, from BRIEF_TEMPLATE_PATH. Not the full client deck —
    see this module's docstring.
    """
    prs = Presentation(str(BRIEF_TEMPLATE_PATH))
    original_slides = list(prs.slides)

    target_slides = []
    for spec in specs:
        src_idx = NARRATIVE_SLIDE_TEMPLATE_INDEX[spec.slide_key]
        target_slides.append(clone_slide(prs, original_slides[src_idx]))

    for spec, slide in zip(specs, target_slides):
        render_narrative_slide(slide, spec, registry, prs)

    # Drop every slide this call didn't ask for (the originals we cloned
    # FROM, plus any other template slide) — reorder_slides only arranges
    # slides, it never removes the ones excluded from `target_slides`.
    sldIdLst = prs.slides._sldIdLst
    target_ids = {id(slide) for slide in target_slides}
    for slide, sldId in list(zip(prs.slides, list(sldIdLst))):
        if id(slide) not in target_ids:
            sldIdLst.remove(sldId)

    reorder_slides(prs, target_slides)
    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()
