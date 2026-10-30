"""Core data model for the deck-generation pipeline.

Fact -> FactRegistry: every number (and every other piece of real, fetched
data — a customer name, a segment label) becomes a Fact, collected in a
registry, so "where did this come from" is always answerable later
(DeckSmith-style provenance — template_id, params, as_of, confidence).

SlideSpec -> DeckPlan: the Deck Planner's output. Structural decisions only
(which section, what type of slide, which data slice) — no slide numbers,
no literal values. Slide position in the final deck is decided later, when
the Renderer actually assembles things in order.

CellSpec/ChartSpec -> SlideContentSpec -> DeckSpec: the Spec Writer's
output. Every data-driven cell is a `fact_id` reference, never a literal —
that's what makes the Validator's job possible: it can mechanically check
"does this fact_id exist" instead of trying to guess whether a string looks
like real data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from pipeline.deck_plan import SlidePlan


# ---------------------------------------------------------------------------
# Facts — the Data Analyst's output
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    id: str
    label: str
    value: Union[float, str]
    unit: str = ""
    source_template: str = ""
    source_params: dict = field(default_factory=dict)
    as_of: str = ""
    confidence: str = "high"


class FactRegistry:
    """Collects every Fact fetched for one deck-build request. Threaded from
    the Data Analyst step through the Deck Planner and Spec Writer, and
    persisted afterwards (keyed by the meeting context's draft ID) so a
    generated deck's numbers stay traceable after the fact.
    """

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._next_id = 1

    def add(
        self,
        *,
        label: str,
        value: Union[float, str],
        unit: str = "",
        source_template: str = "",
        source_params: Optional[dict] = None,
        as_of: str = "",
        confidence: str = "high",
    ) -> str:
        fact_id = f"f{self._next_id}"
        self._next_id += 1
        self._facts[fact_id] = Fact(
            id=fact_id,
            label=label,
            value=value,
            unit=unit,
            source_template=source_template,
            source_params=source_params or {},
            as_of=as_of,
            confidence=confidence,
        )
        return fact_id

    def get(self, fact_id: str) -> Fact:
        return self._facts[fact_id]

    def __contains__(self, fact_id: object) -> bool:
        return fact_id in self._facts

    def __len__(self) -> int:
        return len(self._facts)

    def as_dict(self) -> dict[str, dict]:
        """A plain-dict snapshot of every fact, for persistence/audit."""
        return {fid: vars(fact) for fid, fact in self._facts.items()}


# ---------------------------------------------------------------------------
# DeckPlan — the Deck Planner's output (structure only, no numbers)
# ---------------------------------------------------------------------------


@dataclass
class SlideSpec:
    section: str  # "A", "B", "C", "D/E/F" — matches the Deck Mapping xlsx sections
    slide_type: str  # "cover" | "kpi" | "product_page" | "segment_sales_page" | "segment_share_page" | "deepdive" | "static"
    data_scope: dict = field(default_factory=dict)


@dataclass
class DeckPlan:
    slides: list[SlideSpec] = field(default_factory=list)
    # Computed by the SAME compute_slide_plan tool agent_definitions/
    # deck_planner_agent.py wraps — kept in sync so a future real agent call
    # and today's deterministic math never disagree on what this number means.
    budget: Optional[SlidePlan] = None


# ---------------------------------------------------------------------------
# DeckSpec — the Spec Writer's output (every data value is a fact_id)
# ---------------------------------------------------------------------------


@dataclass
class CellSpec:
    row: int
    col: int
    fact_id: Optional[str] = None  # a data-driven value — must resolve in the FactRegistry
    static_text: Optional[str] = None  # template-fixed text (a header, or a "[%]" data-gap placeholder)
    # A %-change cell derived from two facts (e.g. revenue N-1 -> N). Kept as
    # a pair of references rather than a pre-computed fact so the Data
    # Analyst doesn't have to materialize every possible derived percentage
    # up front — the Validator still checks both facts exist; the Renderer
    # does the one division at format time.
    pct_change_from: Optional[tuple[str, str]] = None  # (previous_fact_id, current_fact_id)

    def is_data_driven(self) -> bool:
        return self.fact_id is not None or self.pct_change_from is not None


@dataclass
class ChartValueSpec:
    fact_id: Optional[str] = None
    sum_of_fact_ids: Optional[list[str]] = None  # e.g. a product's total revenue across seasons

    def referenced_fact_ids(self) -> list[str]:
        if self.fact_id is not None:
            return [self.fact_id]
        return list(self.sum_of_fact_ids or [])


@dataclass
class ChartSeriesSpec:
    name: str
    values: list[ChartValueSpec] = field(default_factory=list)


@dataclass
class ChartSpec:
    category_fact_ids: list[str] = field(default_factory=list)
    series: list[ChartSeriesSpec] = field(default_factory=list)


@dataclass
class SlideContentSpec:
    section: str
    slide_type: str
    source_slide_index: int  # which template slide (0-indexed) this clones/fills from
    cells: list[CellSpec] = field(default_factory=list)
    chart: Optional[ChartSpec] = None
    text_replacements: Optional[dict[str, str]] = None  # token -> fact_id, for non-table text (e.g. cover slide)
    target_row_count: Optional[int] = None  # DATA rows only — never includes the footer
    keep_footer: bool = False  # True only for a segment page's last instance (the TOTAL row)


@dataclass
class DeckSpec:
    slides: list[SlideContentSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Narrative blocks — the Brief Agent's output for the 5 "LLM Generated"
# slides (Commercial Intelligence Brief). Unlike SlideContentSpec, which
# fills a FIXED template shape (one table, maybe one chart), a narrative
# slide is a free-form STACK of blocks the agent chooses from a small menu —
# the visual form isn't fixed, but every value in every block is still a
# fact_id reference, so the same before/after verification (Validator +
# post-render check) still applies. See pipeline/narrative_facts.py for what
# facts exist to choose from, pipeline/narrative_validator.py for the check,
# and pipeline/narrative_renderer.py for how blocks become real pptx shapes.
# ---------------------------------------------------------------------------

ALLOWED_NARRATIVE_CHART_TYPES = ("bar", "column", "line", "pie", "doughnut", "area")


@dataclass
class NarrativeChartBlock:
    chart_type: str  # one of ALLOWED_NARRATIVE_CHART_TYPES
    title: str
    category_fact_ids: list[str] = field(default_factory=list)
    series: list[ChartSeriesSpec] = field(default_factory=list)  # reuses the same Chart*Spec as Section B


@dataclass
class NarrativeTableBlock:
    headers: list[str]
    rows: list[list[CellSpec]] = field(default_factory=list)  # each CellSpec's row/col is ignored — position is list index


@dataclass
class NarrativeKpiBlock:
    label: str
    value_fact_id: str
    delta_from_fact_id: Optional[str] = None  # paired with value_fact_id to show a %-change, like CellSpec.pct_change_from


@dataclass
class NarrativeCalloutBlock:
    """Free text (the one place in the whole deck prose isn't mechanically
    checkable against a fact value) — the Validator can only confirm every
    cited_fact_id exists, never that the text correctly reflects it. That
    gap is exactly what the Content Verifier Agent's judgment is for.
    """

    text: str
    cited_fact_ids: list[str] = field(default_factory=list)


NarrativeBlock = Union[NarrativeChartBlock, NarrativeTableBlock, NarrativeKpiBlock, NarrativeCalloutBlock]


@dataclass
class NarrativeSlideSpec:
    slide_key: str  # "executive_summary" | "account_health" | "portfolio_shifts" | "market_benchmarking" | "operational_risk"
    title: str
    blocks: list[NarrativeBlock] = field(default_factory=list)
