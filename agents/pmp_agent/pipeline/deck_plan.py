"""Client-facing deck slide-allocation logic.

Pure, deterministic arithmetic — no SDK, no LLM, no I/O. This is exactly the
"simple tool" case from the AI Foundry "Tools and Files" doc: a plain
function the model can call, with no session/auth/cleanup needed. It's
wrapped as a ToolDefinition in deck_planner_agent.py.

Scope (confirmed 2026-10-29): the client-facing deck targets ~25 slides.
Slides 9-16 of the French Business Review template (OUTLOOK divider, "Your
priorities," "Prepare next campaign opportunities," "Prepare for next
campaign," "Decisions and next steps," closing, appendix divider, reference
slide) are STATIC — copied verbatim from the template, no DB fetch, no
per-meeting generation. Only slides 1-8 are dynamic, and the only way to use
up slide budget there is by repeating the product/segment patterns on
slides 4, 5+6, and 7 (row caps verified directly against the template via
python-pptx).

This function deliberately does NOT decide the still-parked
top-N-vs-pagination question (see project memory) — when full coverage of
every product/segment would exceed the slide budget, it reports both the
full-coverage count and the overage rather than silently truncating.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Template geometry, verified via python-pptx against the actual French
# template on 2026-10-29 — not estimates.
PRODUCTS_PER_PAGE = 9  # Slide 4 table: header + "PRODUIT A".."PRODUIT I"
SEGMENTS_PER_PAGE = 6  # Slides 5 & 6 table: header + 6 segment rows + TOTAL
PRODUCTS_PER_DEEPDIVE = 7  # Slide 7 pattern: one repeat per segment, "Produit A".."G"

# Updated 2026-10-30 for the RCR template (23 slides, supersedes the older
# 16-slide template as the live one — see pipeline/renderer.TEMPLATE_PATH):
# it adds a "Commercial Intelligence Brief" divider + 5 narrative slides
# right after the cover, and a trailing "Classification" slide at the end.
FIXED_DYNAMIC_SLIDES = 4  # cover, Commercial Intelligence Brief divider, Season Review divider, qualitative review
NARRATIVE_SLIDES = 5  # the Commercial Intelligence Brief's 5 agent-generated slides — fixed count, never paginated, real per-meeting content (not static, not a repeat pattern)
STATIC_SLIDES = 9  # trailing OUTLOOK divider .. appendix .. reference .. Classification slide, verbatim from the template

# Client-facing deck target confirmed 2026-10-29. Supersedes the earlier
# duration-based ~40/45-slide figure for THIS deck specifically — the
# internal sales-rep deck (template not yet shared, parked) is separate and
# not modeled here.
DEFAULT_TARGET_TOTAL_SLIDES = 25


@dataclass
class SlidePlan:
    fixed_dynamic_slides: int
    static_slides: int
    product_review_pages: int  # slide-4 pattern repeats
    segment_review_slides: int  # slide-5 + slide-6 pattern repeats (paired, 2 slides/page)
    deepdive_slides_for_full_coverage: int  # slide-7 pattern repeats, one+ per segment
    total_slides_for_full_coverage: int
    target_total_slides: int
    over_budget: bool  # True if full coverage alone exceeds the target
    overage: int  # total_slides_for_full_coverage - target_total_slides, if positive
    notes: list[str] = field(default_factory=list)


def compute_slide_plan(
    total_focus_products: int,
    total_market_segments: int,
    segment_product_counts: list[int] | None = None,
    target_total_slides: int = DEFAULT_TARGET_TOTAL_SLIDES,
) -> SlidePlan:
    """Compute how many dynamic slides are needed to cover a client's
    product/segment data, against the ~25-slide client-facing deck budget.

    `segment_product_counts`, if given (one entry per market segment, product
    count in that segment), lets deep-dive pagination be computed precisely
    (a segment with more than 7 products needs more than one slide-7 repeat
    to cover it fully). Without it, this assumes one deep-dive slide per
    segment, which is only exact when every segment has <= 7 products.
    """
    notes: list[str] = []

    product_review_pages = math.ceil(total_focus_products / PRODUCTS_PER_PAGE) if total_focus_products else 0
    segment_review_pages = math.ceil(total_market_segments / SEGMENTS_PER_PAGE) if total_market_segments else 0
    segment_review_slides = segment_review_pages * 2  # slide 5 (sales) + slide 6 (share), paired

    if segment_product_counts is not None:
        if len(segment_product_counts) != total_market_segments:
            notes.append(
                "segment_product_counts length does not match total_market_segments; "
                "falling back to one deep-dive slide per segment."
            )
            deepdive_slides = total_market_segments
        else:
            deepdive_slides = sum(math.ceil(count / PRODUCTS_PER_DEEPDIVE) for count in segment_product_counts)
    else:
        deepdive_slides = total_market_segments
        if total_market_segments:
            notes.append(
                "No per-segment product counts given — assumed 1 deep-dive slide per segment; "
                "segments with more than 7 products would actually need more."
            )

    total_for_full_coverage = (
        FIXED_DYNAMIC_SLIDES
        + NARRATIVE_SLIDES
        + STATIC_SLIDES
        + product_review_pages
        + segment_review_slides
        + deepdive_slides
    )
    overage = total_for_full_coverage - target_total_slides
    over_budget = overage > 0

    if over_budget:
        notes.append(
            f"Full portfolio/segment coverage needs {total_for_full_coverage} slides, "
            f"{overage} more than the {target_total_slides}-slide target. This tool does not "
            "decide truncation vs. extending the budget — that decision is explicitly parked "
            "(see project memory); surfacing the conflict rather than silently dropping items."
        )

    return SlidePlan(
        fixed_dynamic_slides=FIXED_DYNAMIC_SLIDES,
        static_slides=STATIC_SLIDES,
        product_review_pages=product_review_pages,
        segment_review_slides=segment_review_slides,
        deepdive_slides_for_full_coverage=deepdive_slides,
        total_slides_for_full_coverage=total_for_full_coverage,
        target_total_slides=target_total_slides,
        over_budget=over_budget,
        overage=max(overage, 0),
        notes=notes,
    )
