"""Tests for the deck Builder (builder.py -> pipeline/*). No LLM/agent/
Portkey involved anywhere in this chain.
"""

import io

from pptx import Presentation

from builder import build_client_deck
from pipeline.renderer import TEMPLATE_PATH

STATIC_TAIL_LENGTH = 9  # OUTLOOK divider..reference..Classification slide — always the deck's last 9 slides (RCR template)


def test_build_client_deck_produces_a_valid_pptx_with_real_numbers() -> None:
    data = build_client_deck("ACTURA", "12 Nov 2026")
    assert len(data) > 10_000  # a real pptx, not an empty stub

    prs = Presentation(io.BytesIO(data))
    slides = list(prs.slides)
    # ACTURA has 9 market segments (2 pages) and 5 products (1 page) in the
    # sample — not a fixed 16, pagination is real now.
    assert len(slides) > 16

    cover_text = "\n".join(shape.text_frame.text for shape in slides[0].shapes if shape.has_text_frame)
    assert "ACTURA" in cover_text
    assert "12 Nov 2026" in cover_text


def test_kpi_table_has_real_revenue_not_placeholder_brackets() -> None:
    data = build_client_deck("ACTURA", "12 Nov 2026")
    prs = Presentation(io.BytesIO(data))
    slide3 = list(prs.slides)[8]  # RCR template: KPI table is 6 slides later (Commercial Intelligence Brief section)
    table = next(shape.table for shape in slide3.shapes if shape.has_table)
    revenue_row = [cell.text for cell in table.rows[1].cells]
    assert "[CA €]" not in revenue_row  # placeholder gone
    assert "€" in revenue_row[1]  # replaced with a real formatted value


def test_market_share_rows_stay_as_gap_placeholders() -> None:
    """Market share has no data source — must not be fabricated."""
    data = build_client_deck("ACTURA", "12 Nov 2026")
    prs = Presentation(io.BytesIO(data))
    slide3 = list(prs.slides)[8]
    table = next(shape.table for shape in slide3.shapes if shape.has_table)
    assert table.rows[2].cells[1].text == "[%]"
    assert table.rows[3].cells[1].text == "[%]"


def test_product_table_filled_with_at_least_one_real_product() -> None:
    data = build_client_deck("ACTURA", "12 Nov 2026")
    prs = Presentation(io.BytesIO(data))
    slide4 = list(prs.slides)[9]  # RCR template: product review is 6 slides later
    table = next(shape.table for shape in slide4.shapes if shape.has_table)
    first_product_row = [cell.text for cell in table.rows[1].cells]
    assert first_product_row[0] not in ("PRODUIT A", "")


def test_no_placeholder_rows_left_beyond_real_data() -> None:
    """ACTURA has 5 real products in the sample — the product page must show
    exactly 6 rows (header + 5), never the template's full 10 with fake
    "PRODUIT F".."I" rows padded in."""
    data = build_client_deck("ACTURA", "12 Nov 2026")
    prs = Presentation(io.BytesIO(data))
    slide4 = list(prs.slides)[9]  # RCR template: product review is 6 slides later
    table = next(shape.table for shape in slide4.shapes if shape.has_table)
    product_names = [table.rows[i].cells[0].text for i in range(1, len(table.rows))]
    assert not any(name.startswith("PRODUIT ") for name in product_names)


def test_all_market_segments_are_covered_across_pages_with_total_on_the_last() -> None:
    """ACTURA has 9 segments, more than the template's 6-row cap — this must
    paginate (not truncate), and only the LAST page carries a TOTAL row that
    reconciles with slide 3's overall KPI."""
    data = build_client_deck("ACTURA", "12 Nov 2026")
    prs = Presentation(io.BytesIO(data))
    slides = list(prs.slides)

    kpi_table = next(s.table for s in slides[8].shapes if s.has_table)
    expected_total = [c.text for c in kpi_table.rows[1].cells][1:4]

    segment_names: list[str] = []
    total_rows_found = 0
    for slide in slides:
        tables = [s.table for s in slide.shapes if s.has_table]
        if not tables:
            continue
        table = tables[0]
        header = [c.text for c in table.rows[0].cells]
        if header[0] != "Segments de marché" or "Ventes" not in header[1]:
            continue  # only the sales table has real revenue — the share table's row 1 header differs
        for row_idx in range(1, len(table.rows)):
            name = table.cell(row_idx, 0).text
            if name == "TOTAL":
                total_rows_found += 1
                assert [table.cell(row_idx, c).text for c in (1, 2, 3)] == expected_total
            else:
                segment_names.append(name)

    assert total_rows_found == 1  # exactly one TOTAL row across all segment-sales pages
    assert len(segment_names) == 9  # every real segment shown, none dropped to fit the template's 6-row cap


def test_segment_share_slide_segment_names_match_sales_slide() -> None:
    """Regression test for a real bug: slide 6 used to keep the template's
    own generic example segment names, unrelated to the actual customer."""
    data = build_client_deck("ACTURA", "12 Nov 2026")
    prs = Presentation(io.BytesIO(data))
    slides = list(prs.slides)

    sales_segments, share_segments = [], []
    for slide in slides:
        tables = [s.table for s in slide.shapes if s.has_table]
        if not tables:
            continue
        table = tables[0]
        header = [c.text for c in table.rows[0].cells]
        names = [table.cell(r, 0).text for r in range(1, len(table.rows)) if table.cell(r, 0).text != "TOTAL"]
        if header[0] == "Segments de marché" and "Ventes" in header[1]:
            sales_segments += names
        elif header[0] == "Segments de marché" and "Part de marché" in header[1]:
            share_segments += names

    assert sales_segments == share_segments
    assert "Insecticides en végétation" not in share_segments  # the template's own unrelated example segment


def test_static_tail_is_untouched_regardless_of_how_many_dynamic_pages_precede_it() -> None:
    """Slides 9-16 of the template (qualitative review onward) are always the
    deck's LAST 8 slides, static and verbatim — wherever pagination makes
    them land, their content must be unchanged from the template."""
    data = build_client_deck("ACTURA", "12 Nov 2026")
    prs = Presentation(io.BytesIO(data))
    slides = list(prs.slides)

    original = Presentation(str(TEMPLATE_PATH))
    original_tail = list(original.slides)[-STATIC_TAIL_LENGTH:]
    built_tail = slides[-STATIC_TAIL_LENGTH:]

    for built_slide, original_slide in zip(built_tail, original_tail):
        built_text = [s.text_frame.text for s in built_slide.shapes if s.has_text_frame]
        original_text = [s.text_frame.text for s in original_slide.shapes if s.has_text_frame]
        assert built_text == original_text
