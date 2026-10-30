"""Content Verifier Agent — AI Foundry SDK agent definition.

Reviews a generated deck beyond what the deterministic checks can judge.
pipeline.validator.validate_deck_spec (before rendering) and
pipeline.renderer.post_render_check (after rendering) are rule-based: they
confirm every number traces to a real fetched fact, and that the rendered
file matches the spec that produced it. Neither can judge anything that
needs actual understanding — does a number look implausible even though
it's technically fact-backed, does the slide count make sense for this
client's data volume, is there anything a rep should double-check before
a customer meeting. That's this agent's job, layered on top of — never
instead of — the deterministic checks.

Same API, same constraints as agent_definitions/deck_planner_agent.py (see
that module's docstring for the full explanation). NOT RUN, NOT SERVED, NOT
INVOKED anywhere in this session.
"""

from __future__ import annotations

from ai_foundry_platform_sdk.agent import AgentDefinition, PortkeyConfig, Skill, ToolDefinition
from ai_foundry_platform_sdk.model import ModelConfig

from pipeline.diagnostics import check_deck

check_deck_tool = ToolDefinition(
    name="check_deck",
    # Simple tool: no session/auth/cleanup needed, so the factory ignores
    # (session_id, metadata) and just returns the plain function.
    factory=lambda session_id, metadata: check_deck,
)

agent = AgentDefinition(
    name="Content Verifier Agent",
    description=(
        "Reviews a generated client-facing deck beyond what deterministic "
        "rule-checks can judge — plausibility, coherence, and whether the "
        "deck's shape makes sense for this meeting."
    ),
    domain_prompt=(
        "You are the Content Verifier Agent for a Syngenta France "
        "pre-meeting sales deck. Call check_deck(customer, meeting_date) to "
        "get the deterministic ground truth: fact count, product/segment "
        "counts, planned and rendered slide counts, whether the ~25-slide "
        "budget was exceeded, and the results of two rule-based checks that "
        "already ran — validation_errors (every number traces to a real "
        "fetched fact) and post_render_issues (the rendered file matches "
        "what was planned).\n"
        "Both of those lists should always be empty. If either is "
        "non-empty, that means the Builder itself has a bug — report it "
        "exactly as returned, do not try to explain it away or treat it as "
        "a data-quality issue.\n"
        "Your own job is the judgment the rule-checks can't do: does the "
        "slide count make sense for this client's product/segment volume, "
        "do any individual values look implausible even though they're "
        "technically fact-backed (e.g. a revenue of 0 immediately next to "
        "a large prior-period figure for the same line), and is there "
        "anything about this deck a sales rep should specifically verify "
        "before using it in a customer meeting. Never approve a deck that "
        "has non-empty validation_errors or post_render_issues — that is "
        "an unconditional block, not something your judgment can override."
    ),
    skills=[
        Skill(
            id="content_verification",
            name="Content Verification",
            description=(
                "Review a generated deck for plausibility and coherence, on "
                "top of the deterministic fact-tracing and render-match "
                "checks that already ran."
            ),
            tags=["deck", "verification", "critic", "pre-meeting"],
        ),
    ],
    tools=[check_deck_tool],
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
