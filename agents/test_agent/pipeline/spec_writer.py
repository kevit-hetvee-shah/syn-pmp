"""Spec Writer: turns a DeckPlan + CustomerFacts into a DeckSpec.

Every data-driven cell becomes a fact_id reference (or a pct_change_from /
sum_of_fact_ids derivation of two-or-more fact_ids) — never a literal value.
This is what makes the Validator's job mechanical rather than a judgment
call: it just checks that every referenced fact_id exists.
"""

from __future__ import annotations

from pipeline.data_analyst import CustomerFacts, ProductFacts, SegmentFacts
from pipeline.models import (
    CellSpec,
    ChartSeriesSpec,
    ChartSpec,
    ChartValueSpec,
    DeckPlan,
    DeckSpec,
    SlideContentSpec,
    SlideSpec,
)

# 0-indexed template slide positions for the slide types that get filled
# (not cloned-and-paginated) — product/segment pages reference these same
# indices as their clone source.
TEMPLATE_SLIDE = {
    "cover": 0,
    "kpi": 2,
    "product_page": 3,
    "segment_sales_page": 4,
    "segment_share_page": 5,
    "deepdive": 6,
}


def write_deck_spec(plan: DeckPlan, facts: CustomerFacts, customer_fact_id: str, meeting_date_fact_id: str) -> DeckSpec:
    slide_specs: list[SlideContentSpec] = []
    for spec in plan.slides:
        if spec.slide_type == "cover":
            slide_specs.append(_cover_spec(customer_fact_id, meeting_date_fact_id))
        elif spec.slide_type == "static":
            slide_specs.append(
                SlideContentSpec(section=spec.section, slide_type="static", source_slide_index=spec.data_scope["template_slide"])
            )
        elif spec.slide_type == "kpi":
            slide_specs.append(_kpi_spec(facts))
        elif spec.slide_type == "product_page":
            slide_specs.append(_product_page_spec(spec, facts))
        elif spec.slide_type == "segment_sales_page":
            slide_specs.append(_segment_sales_spec(spec, facts))
        elif spec.slide_type == "segment_share_page":
            slide_specs.append(_segment_share_spec(spec))
        elif spec.slide_type == "deepdive":
            slide_specs.append(_deepdive_spec(spec, facts))
        else:
            raise ValueError(f"Unknown slide_type: {spec.slide_type}")
    return DeckSpec(slides=slide_specs)


def _cover_spec(customer_fact_id: str, meeting_date_fact_id: str) -> SlideContentSpec:
    return SlideContentSpec(
        section="A",
        slide_type="cover",
        source_slide_index=TEMPLATE_SLIDE["cover"],
        text_replacements={"[Client]": customer_fact_id, "[Date de réunion]": meeting_date_fact_id},
    )


def _kpi_spec(facts: CustomerFacts) -> SlideContentSpec:
    seasons_oldest_first = list(reversed(facts.seasons))
    cells = [CellSpec(row=1, col=i + 1, fact_id=facts.revenue_by_season_fact_ids[s]) for i, s in enumerate(seasons_oldest_first)]
    if len(seasons_oldest_first) >= 2:
        prev_fid = facts.revenue_by_season_fact_ids[seasons_oldest_first[-2]]
        curr_fid = facts.revenue_by_season_fact_ids[seasons_oldest_first[-1]]
        cells.append(CellSpec(row=1, col=4, pct_change_from=(prev_fid, curr_fid)))
    # Rows 2-3 (market share) are left untouched — a confirmed data gap, the
    # template's own "[%]" placeholders stay as-is.
    return SlideContentSpec(section="B", slide_type="kpi", source_slide_index=TEMPLATE_SLIDE["kpi"], cells=cells)


def _product_page_spec(spec: SlideSpec, facts: CustomerFacts) -> SlideContentSpec:
    products: list[ProductFacts] = spec.data_scope["products"]
    product_seasons = facts.seasons[:2]  # this template only has N-1/N columns
    cells: list[CellSpec] = []
    chart_values: list[ChartValueSpec] = []
    for row_idx, product in enumerate(products, start=1):
        season_n, season_n1 = product_seasons[0], product_seasons[1]
        qty_n1 = product.by_season[season_n1]["qty_fact_id"]
        qty_n = product.by_season[season_n]["qty_fact_id"]
        rev_n1 = product.by_season[season_n1]["revenue_fact_id"]
        rev_n = product.by_season[season_n]["revenue_fact_id"]
        cells += [
            CellSpec(row=row_idx, col=0, fact_id=product.name_fact_id),
            CellSpec(row=row_idx, col=1, fact_id=qty_n1),
            CellSpec(row=row_idx, col=2, fact_id=qty_n),
            CellSpec(row=row_idx, col=3, pct_change_from=(qty_n1, qty_n)),
            CellSpec(row=row_idx, col=4, fact_id=rev_n1),
            CellSpec(row=row_idx, col=5, fact_id=rev_n),
            CellSpec(row=row_idx, col=6, pct_change_from=(rev_n1, rev_n)),
        ]
        chart_values.append(ChartValueSpec(sum_of_fact_ids=[rev_n1, rev_n]))

    chart = ChartSpec(
        category_fact_ids=[p.name_fact_id for p in products],
        series=[ChartSeriesSpec(name="CA produit saison", values=chart_values)],
    )
    return SlideContentSpec(
        section="B",
        slide_type="product_page",
        source_slide_index=TEMPLATE_SLIDE["product_page"],
        cells=cells,
        chart=chart,
        target_row_count=len(products),
    )


def _segment_sales_spec(spec: SlideSpec, facts: CustomerFacts) -> SlideContentSpec:
    segments: list[SegmentFacts] = spec.data_scope["segments"]
    is_last_page: bool = spec.data_scope["is_last_page"]
    seasons_oldest_first = list(reversed(facts.seasons))

    cells: list[CellSpec] = []
    for row_idx, segment in enumerate(segments, start=1):
        cells.append(CellSpec(row=row_idx, col=0, fact_id=segment.name_fact_id))
        for col, season in enumerate(seasons_oldest_first):
            cells.append(CellSpec(row=row_idx, col=col + 1, fact_id=segment.by_season[season]))
        if len(seasons_oldest_first) >= 2:
            prev_fid = segment.by_season[seasons_oldest_first[-2]]
            curr_fid = segment.by_season[seasons_oldest_first[-1]]
            cells.append(CellSpec(row=row_idx, col=4, pct_change_from=(prev_fid, curr_fid)))

    if is_last_page:
        total_row = len(segments) + 1  # the row right after the last data row
        # Explicit, not assumed: relying on "the template's own footer row
        # already says TOTAL" turned out false once row-growth/shrink made
        # the footer a cloned/shifted row rather than always the pristine
        # original — making it an explicit CellSpec means both the Renderer
        # sets it deterministically *and* post_render_check actually verifies
        # it, instead of silently trusting an assumption that already broke
        # once.
        cells.append(CellSpec(row=total_row, col=0, static_text="TOTAL"))
        for col, season in enumerate(seasons_oldest_first):
            cells.append(CellSpec(row=total_row, col=col + 1, fact_id=facts.revenue_by_season_fact_ids[season]))
        if len(seasons_oldest_first) >= 2:
            prev_fid = facts.revenue_by_season_fact_ids[seasons_oldest_first[-2]]
            curr_fid = facts.revenue_by_season_fact_ids[seasons_oldest_first[-1]]
            cells.append(CellSpec(row=total_row, col=4, pct_change_from=(prev_fid, curr_fid)))

    return SlideContentSpec(
        section="B",
        slide_type="segment_sales_page",
        source_slide_index=TEMPLATE_SLIDE["segment_sales_page"],
        cells=cells,
        target_row_count=len(segments),  # DATA rows only — the footer (if kept) is handled separately
        keep_footer=is_last_page,
    )


def _segment_share_spec(spec: SlideSpec) -> SlideContentSpec:
    """Slide 6: no data source for the %-values (confirmed gap — left as the
    template's "[%]" placeholders). Only the segment NAMES are real, synced
    to the same list used on the sales page — fixes the bug where this slide
    kept the template's own unrelated example segments.
    """
    segments: list[SegmentFacts] = spec.data_scope["segments"]
    is_last_page: bool = spec.data_scope["is_last_page"]
    cells = [CellSpec(row=row_idx, col=0, fact_id=segment.name_fact_id) for row_idx, segment in enumerate(segments, start=1)]
    return SlideContentSpec(
        section="B",
        slide_type="segment_share_page",
        source_slide_index=TEMPLATE_SLIDE["segment_share_page"],
        cells=cells,
        target_row_count=len(segments),
        keep_footer=is_last_page,
    )


def _deepdive_spec(spec: SlideSpec, facts: CustomerFacts) -> SlideContentSpec:
    segment_name: str = spec.data_scope["segment_name"]
    products: list[ProductFacts] = spec.data_scope["products"]
    seasons_oldest_first = list(reversed(facts.seasons))

    segment_name_fact_id = next((s.name_fact_id for s in facts.segments if s.name == segment_name), None)

    cells: list[CellSpec] = []
    if segment_name_fact_id:
        cells.append(CellSpec(row=0, col=0, fact_id=segment_name_fact_id))

    chart_series_values: dict[str, list[ChartValueSpec]] = {s: [] for s in seasons_oldest_first}
    for row_idx, product in enumerate(products, start=1):
        cells.append(CellSpec(row=row_idx, col=0, fact_id=product.name_fact_id))
        for col, season in enumerate(seasons_oldest_first):
            fid = product.by_season[season]["qty_fact_id"]
            cells.append(CellSpec(row=row_idx, col=col + 1, fact_id=fid))
            chart_series_values[season].append(ChartValueSpec(fact_id=fid))
        if len(seasons_oldest_first) >= 1:
            n_minus_2 = product.by_season[seasons_oldest_first[0]]["qty_fact_id"]
            n = product.by_season[seasons_oldest_first[-1]]["qty_fact_id"]
            cells.append(CellSpec(row=row_idx, col=4, pct_change_from=(n_minus_2, n)))
        if len(seasons_oldest_first) >= 2:
            n_minus_1 = product.by_season[seasons_oldest_first[-2]]["qty_fact_id"]
            n = product.by_season[seasons_oldest_first[-1]]["qty_fact_id"]
            cells.append(CellSpec(row=row_idx, col=5, pct_change_from=(n_minus_1, n)))

    chart = ChartSpec(
        category_fact_ids=[p.name_fact_id for p in products],
        series=[ChartSeriesSpec(name=season, values=chart_series_values[season]) for season in reversed(seasons_oldest_first)],
    )
    return SlideContentSpec(
        section="B",
        slide_type="deepdive",
        source_slide_index=TEMPLATE_SLIDE["deepdive"],
        cells=cells,
        chart=chart,
        target_row_count=len(products),
    )
