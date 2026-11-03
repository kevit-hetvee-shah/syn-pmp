"""Brief Agent — LangGraph version (replaces agent_definitions/brief_agent.py's
AI Foundry SDK AgentDefinition + Strands `@tool`).

Generates the 5 "LLM Generated" slides from the RCR-reviewed template's
Commercial Intelligence Brief section (Executive Summary, Account Health,
Portfolio Shifts, Market Benchmarking, Operational Risk). Per the 2026-10-30
ideation on this template: the VISUAL FORM for these slides is deliberately
NOT fixed — unlike Section B (KPI/product/segment tables, always the same
template shape), this agent chooses which blocks to use (chart, table, KPI
callout, free-text callout) and, for charts, which chart type — whatever
best presents the facts it's given for that one slide.

That freedom is bounded, not unlimited, for the same reason every other
part of this deck is: ALLOWED_NARRATIVE_CHART_TYPES in pipeline/models.py is
the full menu of chart types pipeline/narrative_renderer.py can actually
render as a native, editable pptx chart. And every value shown, in any
block, must be a fact_id the get_narrative_brief_inputs tool actually handed
back — this agent decides PRESENTATION, never arithmetic; pipeline/
narrative_facts.py (the Narrative Analyst) is the only place deltas/
rankings/labels get computed, and pipeline/narrative_validator.py
mechanically rejects any fact_id this agent didn't receive.

This is the ONE agent actually invoked for real (via pipeline/
narrative_agent_runner.py). `build_brief_agent(facts)` builds a fresh
compiled graph per deck build whose tool is bound (by closure) to that
build's own already-fetched CustomerFacts/FactRegistry — deliberately NOT
re-fetching inside the tool, so every fact_id this agent cites is guaranteed
to exist in the SAME registry pipeline/renderer.py and pipeline/validator.py
check against (a second independent fetch_customer_facts() call would create
a different FactRegistry instance with different fact_ids — a real
correctness trap this avoids by construction rather than by convention).

`response_format=NarrativeSlideSpecModel` makes `langchain.agents.create_agent`'s
agent do a final constrained-output call once its tool-use loop ends,
putting the parsed Pydantic model on the compiled graph's result under the
`structured_response` key — see narrative_agent_runner.py for the
Pydantic-to-dataclass conversion that happens with that result.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph

from llm import get_chat_model
from pipeline.data_analyst import CustomerFacts
from pipeline.models import ALLOWED_NARRATIVE_CHART_TYPES
from pipeline.narrative_facts import NARRATIVE_SLIDE_KEYS, compute_narrative_facts
from pipeline.narrative_output_schema import NarrativeSlideSpecModel

NAME = "Brief Agent"
DESCRIPTION = (
    "Generates the Commercial Intelligence Brief's 5 narrative slides, choosing its own "
    "visual presentation (chart, table, KPI callout, or text callout) per slide from the "
    "facts it's given — never inventing a number itself."
)

DOMAIN_PROMPT = (
    "You are the Brief Agent for a Syngenta France pre-meeting sales deck. For "
    "the slide_key you're asked to generate, call get_narrative_brief_inputs(slide_key) "
    "first.\n"
    "If groundable=False: do not fabricate content for that slide. Your returned slide "
    "must still have EXACTLY ONE block — a single callout block whose text states plainly "
    "that this slide can't be generated yet and gives the 'reason' field's explanation. "
    "Never return zero blocks, even when nothing is groundable — an empty slide is not an "
    "acceptable way to say 'not available'; a callout saying so is.\n"
    "If groundable=True, you get a `facts` dict (name -> {fact_id, value, unit, kind}), "
    "a `caveats` list of things you must NOT claim or compute yourself, and the "
    "menu of block/chart types you're allowed to use. Every fact's `kind` is either "
    "'number' or 'text' — check it. A KPI block's value_fact_id/delta_from_fact_id, a "
    "chart series' values, and a table cell's pct_change_from pair ALL require a fact "
    "whose kind is 'number'. A 'text' fact (a trajectory label like 'growing', a "
    "product/segment name) belongs in a callout's prose or a table's plain fact_id "
    "cell instead — NEVER in a numeric slot, even if it seems like the most important "
    "fact for that slide. Your job:\n"
    "- Decide which block(s) best present these specific facts — a KPI callout for "
    "a single headline number, a chart for a comparison across categories, a table "
    "for several parallel rows, free text for the narrative/recommendation. Pick "
    "whatever fits the data; there is no single required layout for this slide.\n"
    "- If you use a chart, pick the chart_type (from allowed_chart_types) that best "
    "fits the data's shape — e.g. a trend across seasons suits a line or column "
    "chart, a few named items suit bar or column, a share-of-whole suits doughnut "
    "or pie. Never pick a type that misrepresents the data's shape.\n"
    "- EVERY number you display, in any block, must be one of the fact_ids you were "
    "given. Never compute a new figure yourself, even a simple one (a sum, a second "
    "delta, a percentage) — if you need a derived number that wasn't provided, that "
    "means it isn't available yet; say so in the callout text instead of inventing it.\n"
    "- Respect every caveat exactly — they exist because a specific fabrication risk "
    "was identified for this slide (e.g. a unit-of-measure mismatch, a missing "
    "product classification); do not work around a caveat by phrasing around it.\n"
    "Return your slide as blocks (chart/table/kpi/callout), each block's data given "
    "as fact_id references, never literal numbers."
)


def _make_get_narrative_brief_inputs(facts: CustomerFacts):
    """Builds the tool function for ONE deck build, closing over that
    build's already-fetched `facts` instead of re-fetching — see this
    module's docstring for why that matters."""

    @tool
    def get_narrative_brief_inputs(slide_key: str) -> dict:
        """The deterministic ground truth for ONE narrative slide — every
        fact this agent is allowed to reference, any caveats it must respect
        by NOT computing/inventing a number instead, and the menu of
        block/chart types it may choose from. Deciding how to present this
        (which blocks, which chart type, how to phrase the narrative) is the
        agent's job; which numbers exist is not.

        Args:
            slide_key: which Commercial Intelligence Brief slide to fetch
                inputs for — one of executive_summary, account_health,
                portfolio_shifts, market_benchmarking, operational_risk.
        """
        if slide_key not in NARRATIVE_SLIDE_KEYS:
            return {"error": f"unknown slide_key '{slide_key}' (expected one of {NARRATIVE_SLIDE_KEYS})"}

        narrative = compute_narrative_facts(slide_key, facts)
        if not narrative.groundable:
            return {
                "slide_key": slide_key,
                "groundable": False,
                "reason": narrative.reason_not_groundable,
            }

        return {
            "slide_key": slide_key,
            "groundable": True,
            "facts": {
                name: {
                    "fact_id": fid,
                    "value": facts.registry.get(fid).value,
                    "unit": facts.registry.get(fid).unit,
                    # Explicit, not left for you to infer from the name or
                    # value — a numeric slot (KPI value/delta, a chart
                    # series value, a table pct_change_from pair) MUST only
                    # ever reference a fact whose kind is "number". A "text"
                    # fact (e.g. a trajectory label like 'growing', or a
                    # product/segment name) belongs in callout prose or a
                    # table's plain fact_id cell instead.
                    "kind": "number" if isinstance(facts.registry.get(fid).value, (int, float)) else "text",
                }
                for name, fid in narrative.facts.items()
            },
            "caveats": narrative.caveats,
            "allowed_block_types": ["chart", "table", "kpi", "callout"],
            "allowed_chart_types": list(ALLOWED_NARRATIVE_CHART_TYPES),
        }

    return get_narrative_brief_inputs


def build_brief_agent(facts: CustomerFacts) -> CompiledStateGraph:
    """One fresh compiled graph per deck build, its tool bound to `facts`.
    Cheap to build repeatedly except for the model-client credential
    resolution `get_chat_model()` does — see conversation_agent.py's
    docstring for why that's unavoidable at build time."""
    tool_fn = _make_get_narrative_brief_inputs(facts)
    return create_agent(
        model=get_chat_model(),
        tools=[tool_fn],
        system_prompt=DOMAIN_PROMPT,
        response_format=NarrativeSlideSpecModel,
        name=NAME,
    )
