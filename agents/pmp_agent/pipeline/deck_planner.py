"""Deck Planner: decides the deck's STRUCTURE from fetched fact volumes —
which sections, how many pages, which segment gets a deep-dive. Produces a
DeckPlan (section-tagged slide specs, no slide numbers, no literal values —
slide position in the final deck is decided later, by the Renderer).

Deterministic today (same top-N/fetch-all rules used before this refactor,
just organized as explicit plan-building instead of hardcoded slide
indices). This is the one function meant to become a real call into
agent_definitions/deck_planner_agent.py later — nothing else in the
pipeline needs to change when that happens: the Spec Writer, Validator and
Renderer only ever consume a DeckPlan, never call data_access directly.

Wired (2026-10-31) to actually call `compute_slide_plan` — the same tool
agent_definitions/deck_planner_agent.py exposes to a real agent — so the
deterministic path today and a real agent call later are never computing
budget diagnostics two different ways. Segments are paginated in full (no
truncation) regardless of what the budget check reports; `over_budget`
is attached to the plan as information for a human/future-agent decision,
never used here to silently drop anything.
"""

from __future__ import annotations

import math

from pipeline.data_analyst import CustomerFacts
from pipeline.deck_plan import PRODUCTS_PER_DEEPDIVE, PRODUCTS_PER_PAGE, SEGMENTS_PER_PAGE, compute_slide_plan
from pipeline.models import DeckPlan, SlideSpec
from pipeline.narrative_facts import NARRATIVE_SLIDE_KEYS

# 0-indexed positions in the RCR template (23 slides — see
# pipeline/renderer.TEMPLATE_PATH) that are always copied verbatim, never
# regenerated: the "Commercial Intelligence Brief" divider right after the
# cover, the "Season Review" divider right after the 5 narrative slides, the
# qualitative-review slide (no data source), and sections E/F + the
# closing/appendix/reference/Classification slides.
STATIC_SLIDE_AFTER_COVER = 1
STATIC_SLIDE_AFTER_NARRATIVE = 7
STATIC_SLIDE_AFTER_SECTION_B = 13
STATIC_SLIDES_TAIL = list(range(14, 23))


def plan_deck(facts: CustomerFacts) -> DeckPlan:
    slides: list[SlideSpec] = []

    # Section A — meeting context
    slides.append(SlideSpec(section="A", slide_type="cover", data_scope={}))
    slides.append(SlideSpec(section="A", slide_type="static", data_scope={"template_slide": STATIC_SLIDE_AFTER_COVER}))

    # Commercial Intelligence Brief — 5 agent-generated narrative slides
    # (Executive Summary, Account Health, Portfolio Shifts, Market
    # Benchmarking, Operational Risk). Structural placeholder only — no
    # literal content here, same "no numbers in the plan" rule as every
    # other slide type; the actual NarrativeSlideSpec (from a real Brief
    # Agent call) is attached later in pipeline.spec_writer.
    for slide_key in NARRATIVE_SLIDE_KEYS:
        slides.append(SlideSpec(section="Narrative", slide_type="narrative", data_scope={"slide_key": slide_key}))
    slides.append(SlideSpec(section="A", slide_type="static", data_scope={"template_slide": STATIC_SLIDE_AFTER_NARRATIVE}))

    # Section B — commercial performance
    slides.append(SlideSpec(section="B", slide_type="kpi", data_scope={}))

    product_pages = math.ceil(len(facts.products) / PRODUCTS_PER_PAGE) or 1
    for page in range(product_pages):
        chunk = facts.products[page * PRODUCTS_PER_PAGE : (page + 1) * PRODUCTS_PER_PAGE]
        slides.append(SlideSpec(section="B", slide_type="product_page", data_scope={"page": page, "products": chunk}))

    segment_pages = math.ceil(len(facts.segments) / SEGMENTS_PER_PAGE) or 1
    for page in range(segment_pages):
        chunk = facts.segments[page * SEGMENTS_PER_PAGE : (page + 1) * SEGMENTS_PER_PAGE]
        is_last = page == segment_pages - 1
        slides.append(
            SlideSpec(
                section="B",
                slide_type="segment_sales_page",
                data_scope={"page": page, "segments": chunk, "is_last_page": is_last},
            )
        )
    for page in range(segment_pages):
        chunk = facts.segments[page * SEGMENTS_PER_PAGE : (page + 1) * SEGMENTS_PER_PAGE]
        is_last = page == segment_pages - 1
        slides.append(
            SlideSpec(
                section="B",
                slide_type="segment_share_page",
                data_scope={"page": page, "segments": chunk, "is_last_page": is_last},
            )
        )

    for segment_name, products in facts.top_segment_products.items():
        chunk = products[:PRODUCTS_PER_DEEPDIVE]
        slides.append(
            SlideSpec(section="B", slide_type="deepdive", data_scope={"segment_name": segment_name, "products": chunk})
        )

    # Section D (qualitative review) — no data source, static for now
    slides.append(SlideSpec(section="D", slide_type="static", data_scope={"template_slide": STATIC_SLIDE_AFTER_SECTION_B}))

    # Sections E/F + structural (OUTLOOK divider, priorities, opportunities,
    # decisions, closing, appendix, reference) — static, per the user's
    # 2026-10-30 scope decision.
    for template_slide in STATIC_SLIDES_TAIL:
        slides.append(SlideSpec(section="E/F", slide_type="static", data_scope={"template_slide": template_slide}))

    budget = compute_slide_plan(total_focus_products=len(facts.products), total_market_segments=len(facts.segments))
    return DeckPlan(slides=slides, budget=budget)
