"""Brief Agent — AI Foundry SDK agent definition.

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
render as a native, editable pptx chart (python-pptx has no native
map/waterfall/funnel chart — out of scope here, confirmed with the user:
"whatever fits data, not actual map"). And every value shown, in any block,
must be a fact_id the get_narrative_brief_inputs tool actually handed back —
this agent decides PRESENTATION, never arithmetic; pipeline/narrative_facts.py
(the Narrative Analyst) is the only place deltas/rankings/labels get computed,
and pipeline/narrative_validator.py mechanically rejects any fact_id this
agent didn't receive.

Same API, same constraints as agent_definitions/deck_planner_agent.py (see
that module's docstring for the full explanation): ToolDefinition as a
"simple tool", Skill as capability metadata, and NOT RUN, NOT SERVED, NOT
INVOKED anywhere in this session. The generation step itself (turning
get_narrative_brief_inputs' output into a NarrativeSlideSpec) therefore
can't be exercised end to end here — pipeline/narrative_facts.py,
pipeline/narrative_validator.py, and pipeline/narrative_renderer.py are each
fully tested SDK-free, against hand-built NarrativeSlideSpec instances that
stand in for what this agent would eventually return.
"""

from __future__ import annotations

from ai_foundry_platform_sdk.agent import AgentDefinition, PortkeyConfig, Skill, ToolDefinition
from ai_foundry_platform_sdk.model import ModelConfig

from pipeline.data_analyst import fetch_customer_facts
from pipeline.models import ALLOWED_NARRATIVE_CHART_TYPES
from pipeline.narrative_facts import NARRATIVE_SLIDE_KEYS, compute_narrative_facts


def get_narrative_brief_inputs(customer: str, slide_key: str) -> dict:
    """Agent-callable tool: the deterministic ground truth for ONE narrative
    slide — every fact this agent is allowed to reference, any caveats it
    must respect by NOT computing/inventing a number instead, and the menu
    of block/chart types it may choose from. Deciding how to present this
    (which blocks, which chart type, how to phrase the narrative) is the
    agent's job; which numbers exist is not.
    """
    if slide_key not in NARRATIVE_SLIDE_KEYS:
        return {"error": f"unknown slide_key '{slide_key}' (expected one of {NARRATIVE_SLIDE_KEYS})"}

    facts = fetch_customer_facts(customer)
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
            name: {"fact_id": fid, "value": facts.registry.get(fid).value, "unit": facts.registry.get(fid).unit}
            for name, fid in narrative.facts.items()
        },
        "caveats": narrative.caveats,
        "allowed_block_types": ["chart", "table", "kpi", "callout"],
        "allowed_chart_types": list(ALLOWED_NARRATIVE_CHART_TYPES),
    }


get_narrative_brief_inputs_tool = ToolDefinition(
    name="get_narrative_brief_inputs",
    # Simple tool: no session/auth/cleanup needed, so the factory ignores
    # (session_id, metadata) and just returns the plain function.
    factory=lambda session_id, metadata: get_narrative_brief_inputs,
)

agent = AgentDefinition(
    name="Brief Agent",
    description=(
        "Generates the Commercial Intelligence Brief's 5 narrative slides, choosing "
        "its own visual presentation (chart, table, KPI callout, or text callout) "
        "per slide from the facts it's given — never inventing a number itself."
    ),
    domain_prompt=(
        "You are the Brief Agent for a Syngenta France pre-meeting sales deck. For "
        "a given (customer, slide_key), call get_narrative_brief_inputs(customer, "
        "slide_key) first.\n"
        "If groundable=False: do not fabricate content for that slide. State plainly "
        "that this slide can't be generated yet and why (the 'reason' field), and stop.\n"
        "If groundable=True, you get a `facts` dict (name -> {fact_id, value, unit}), "
        "a `caveats` list of things you must NOT claim or compute yourself, and the "
        "menu of block/chart types you're allowed to use. Your job:\n"
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
    ),
    skills=[
        Skill(
            id="narrative_brief_generation",
            name="Narrative Brief Generation",
            description=(
                "Generate one Commercial Intelligence Brief slide's content and visual "
                "presentation from the facts available for it, grounding every displayed "
                "number in a real fact_id."
            ),
            tags=["deck", "narrative", "brief", "pre-meeting"],
        ),
    ],
    tools=[get_narrative_brief_inputs_tool],
    model_config=ModelConfig(model_id="@az-openai/gpt-4.1-mini"),
    portkey=PortkeyConfig(
        allow_caller_kwargs=True,
        debug_logging=False,
    ),
)

# Deliberately not called in this session:
#   from ai_foundry_platform_sdk.app import create_agui_app
#   app = create_agui_app(agent, ...)
# Serving/invoking this agent would route through Portkey and incur cost.
