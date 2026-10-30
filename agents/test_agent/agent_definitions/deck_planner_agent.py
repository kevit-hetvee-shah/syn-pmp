"""Deck Planner Agent — AI Foundry SDK agent definition.

This is a separate agent in the pipeline from the one served by app.py
(which covers wizard step 1, Meeting Context / Conversation Agent). This
module defines the Deck Planner Agent's AgentDefinition, following the exact
API documented in "Building Your Agent" and "Tools and Files" (AI Foundry
Platform SDK docs, read 2026-10-29):

  - `ToolDefinition(name=str, factory=callable)` — a "simple tool": the
    factory takes `(session_id, metadata)` and returns the tool. For a
    tool with no session/auth/cleanup needs (this one — pure arithmetic),
    the factory just ignores its arguments and returns the function.
  - `Skill(id=, name=, description=, tags=)` — four fields, advertised
    capability metadata, no logic of its own.

NOT RUN, NOT SERVED, NOT INVOKED anywhere in this session — this module only
defines the agent. Nothing here calls `create_agui_app`, `build_agent`, or
any other execution path, so it cannot reach Portkey or incur model cost.
It also cannot be import-tested locally right now: `ai_foundry_platform_sdk`
isn't installed in this repo's .venv (see test-agent-local-dev-setup memory —
the private GitLab package index isn't configured yet), so this file is
written to match the documented API exactly but is unverified by execution.
`pipeline/deck_plan.py`'s own logic IS fully tested (tests/pipeline/test_deck_plan.py, SDK-free).

Multi-agent note: the AI Foundry SDK has its own in-process composition
primitive, `build_agent(agent_def, model_provider=, session_id=)`, used as a
context manager exposing `.agent(message)` — suited to sequential pipelines,
parallel fan-out, or a router. The existing architecture diagrams for this
project specify LangGraph as the overall pipeline orchestrator; that's not
necessarily in conflict with `build_agent` — LangGraph could still own the
overall graph/state while each node uses `build_agent` to run an
SDK-managed sub-agent in-process. Worth deciding explicitly once
orchestration is actually built; not resolved here.

UPDATE 2026-10-31: pipeline/deck_planner.py now calls `compute_slide_plan`
directly for budget diagnostics, so this agent's tool and the live
deterministic path are the same code, not two parallel implementations.
Also, segments are no longer capped/truncated at all (pipeline/renderer.py
paginates them in full via real slide cloning) — the domain_prompt below is
updated to reflect that the "don't silently drop" instruction now applies
to products (still capped at 9/page) and to the overall slide-count budget,
not to segment coverage, which is a solved problem now.
"""

from __future__ import annotations

from ai_foundry_platform_sdk.agent import AgentDefinition, PortkeyConfig, Skill, ToolDefinition
from ai_foundry_platform_sdk.model import ModelConfig

from pipeline.deck_plan import compute_slide_plan

compute_slide_plan_tool = ToolDefinition(
    name="compute_slide_plan",
    # Simple tool: no session/auth/cleanup needed, so the factory ignores
    # (session_id, metadata) and just returns the plain function.
    factory=lambda session_id, metadata: compute_slide_plan,
)

agent = AgentDefinition(
    name="Deck Planner Agent",
    description=(
        "Plans the client-facing Business Review & Outlook deck's slide "
        "structure: decides how many times to repeat the product-review, "
        "segment-review, and segment-deep-dive slide patterns to cover a "
        "client's data within the ~25-slide target."
    ),
    domain_prompt=(
        "You are the Deck Planner Agent for a Syngenta France pre-meeting "
        "sales deck. The client-facing deck has a fixed SECTION structure "
        "(A: meeting context, B: commercial performance, D/E/F: static/"
        "manual) — think in sections, never in fixed slide numbers, since "
        "how many slides Section B produces depends on the client's data.\n"
        "- Section A's cover and divider are single slides. Sections D/E/F "
        "are STATIC — copied verbatim from the template. Never regenerate "
        "or alter them, never fetch data for them.\n"
        "- Section B's product-review and segment-review (sales+share, "
        "paired) patterns repeat to cover ALL of the client's data — every "
        "market segment is shown, paginated across as many slides as "
        "needed, never truncated to fit a budget. Products are capped at "
        "the template's per-page row limit; the segment deep-dive covers "
        "one chosen segment per repeat.\n"
        "Call the compute_slide_plan tool with the client's product and "
        "segment counts to see the resulting slide-count estimate against "
        "the ~25-slide target. If it reports over_budget=true, that is "
        "informational, not a reason to drop content — surface it for the "
        "sales rep or a human reviewer to decide, per the project's parked "
        "decision on how large decks should be handled."
    ),
    skills=[
        Skill(
            id="deck_planning",
            name="Deck Planning",
            description=(
                "Compute how the client-facing deck's dynamic slides (product "
                "review, segment review, segment deep-dive) should repeat to "
                "cover a client's data within the slide budget."
            ),
            tags=["deck", "planning", "pre-meeting"],
        ),
    ],
    tools=[compute_slide_plan_tool],
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
