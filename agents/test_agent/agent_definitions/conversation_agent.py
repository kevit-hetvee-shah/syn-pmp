"""Conversation Agent — AI Foundry SDK agent definition.

Checks whether a meeting-context draft has enough REAL context to proceed —
not just whether the required fields are filled in. readiness.py's
check_readiness() deliberately only checks presence (is a field non-empty);
its own docstring names this exact agent as the extension point for
judging sufficiency/clarity, which pure presence-checking code can't do (an
objective like "discuss business" passes every presence check while being
useless to the Deck Planner).

Same API, same constraints as agent_definitions/deck_planner_agent.py (see
that module's docstring for the full explanation): ToolDefinition as a
"simple tool", Skill as capability metadata, and NOT RUN, NOT SERVED, NOT
INVOKED anywhere in this session — defining the agent cannot reach Portkey
or incur model cost; only create_agui_app/build_agent would.
"""

from __future__ import annotations

from ai_foundry_platform_sdk.agent import AgentDefinition, PortkeyConfig, Skill, ToolDefinition
from ai_foundry_platform_sdk.model import ModelConfig

import storage
from readiness import check_readiness


def check_context_readiness(draft_id: str) -> dict:
    """Agent-callable tool: the deterministic ground truth (which required
    fields are present, plus the actual text of the free-form ones) for one
    meeting-context draft. Judging whether that text is specific enough is
    the agent's job, not this function's — see readiness.py's docstring.
    """
    record = storage.get_draft(draft_id)
    if record is None:
        return {"error": f"draft '{draft_id}' not found"}
    result = check_readiness(record)
    return {
        "ready_count": result.ready_count,
        "required_count": result.required_count,
        "all_fields_present": result.all_ready,
        "missing_fields": [f.field for f in result.fields if not f.ready],
        "objectives": record.objectives,
        "hook": record.hook,
    }


check_context_readiness_tool = ToolDefinition(
    name="check_context_readiness",
    # Simple tool: no session/auth/cleanup needed, so the factory ignores
    # (session_id, metadata) and just returns the plain function.
    factory=lambda session_id, metadata: check_context_readiness,
)

agent = AgentDefinition(
    name="Conversation Agent",
    description=(
        "Checks whether a sales rep's meeting-context draft has enough "
        "real context to proceed — not just whether the required fields "
        "are filled in, but whether what's there is specific and usable."
    ),
    domain_prompt=(
        "You are the Conversation Agent for a Syngenta France pre-meeting "
        "sales deck. Call check_context_readiness(draft_id) to see which "
        "required fields are present and read the rep's actual objectives "
        "and hook text.\n"
        "Field presence alone is not enough: an objective like 'discuss "
        "business' or a hook like 'catch up' is technically filled in but "
        "gives the Deck Planner and Brief agents nothing to work with. "
        "Judge whether the objective is specific enough to act on (ties to "
        "a concrete outcome, not a vague topic) and whether the hook "
        "actually references something real about this customer. If "
        "fields are missing OR present-but-vague, ask the rep one "
        "targeted follow-up question at a time — never more than one, and "
        "never ask about a field that's already specific and usable. Do "
        "not fabricate what a good answer would look like; ask for it."
    ),
    skills=[
        Skill(
            id="context_sufficiency",
            name="Context Sufficiency Check",
            description=(
                "Judge whether a meeting-context draft has enough specific, "
                "usable information to proceed — not just whether required "
                "fields are non-empty."
            ),
            tags=["conversation", "context", "pre-meeting"],
        ),
    ],
    tools=[check_context_readiness_tool],
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
