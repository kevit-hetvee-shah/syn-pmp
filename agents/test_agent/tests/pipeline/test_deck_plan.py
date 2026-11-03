"""Tests for the deterministic slide-allocation arithmetic in deck_plan.py.

No SDK dependency — pure function, runs anywhere.
"""

from pipeline.deck_plan import DEFAULT_TARGET_TOTAL_SLIDES, compute_slide_plan


def test_small_client_fits_comfortably_within_budget() -> None:
    plan = compute_slide_plan(total_focus_products=5, total_market_segments=2)
    assert plan.product_review_pages == 1
    assert plan.segment_review_slides == 2  # 1 page of segments -> slide 5 + slide 6
    assert plan.deepdive_slides_for_full_coverage == 2  # 1 per segment, no counts given
    assert plan.total_slides_for_full_coverage == 4 + 5 + 9 + 1 + 2 + 2  # 23 (RCR template)
    assert plan.over_budget is False
    assert plan.overage == 0


def test_large_portfolio_flags_overage_without_truncating() -> None:
    # Matches the sample data finding: a real client can have 16 products / 8 segments.
    plan = compute_slide_plan(total_focus_products=16, total_market_segments=8)
    assert plan.product_review_pages == 2  # ceil(16/9)
    assert plan.segment_review_slides == 4  # ceil(8/6)=2 pages * 2 slides
    assert plan.deepdive_slides_for_full_coverage == 8  # 1 per segment (no detail given)
    expected_total = 4 + 5 + 9 + 2 + 4 + 8  # 32 (RCR template)
    assert plan.total_slides_for_full_coverage == expected_total
    assert plan.target_total_slides == DEFAULT_TARGET_TOTAL_SLIDES
    assert plan.over_budget == (expected_total > DEFAULT_TARGET_TOTAL_SLIDES)


def test_per_segment_product_counts_refine_deepdive_pagination() -> None:
    # One segment has 10 products -> needs 2 deep-dive slides (ceil(10/7)), not 1.
    plan = compute_slide_plan(
        total_focus_products=12,
        total_market_segments=2,
        segment_product_counts=[10, 2],
    )
    assert plan.deepdive_slides_for_full_coverage == 2 + 1  # ceil(10/7) + ceil(2/7)


def test_over_budget_is_reported_not_silently_truncated() -> None:
    plan = compute_slide_plan(total_focus_products=50, total_market_segments=15, target_total_slides=25)
    assert plan.over_budget is True
    assert plan.overage > 0
    assert any("does not decide truncation" in n for n in plan.notes)


def test_mismatched_segment_counts_length_falls_back_gracefully() -> None:
    plan = compute_slide_plan(
        total_focus_products=5,
        total_market_segments=3,
        segment_product_counts=[1, 2],  # wrong length on purpose
    )
    assert plan.deepdive_slides_for_full_coverage == 3  # fell back to 1/segment
    assert any("falling back" in n for n in plan.notes)
