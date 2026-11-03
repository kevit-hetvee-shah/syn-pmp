"""Conversation Agent — LangGraph version (replaces agent_definitions/
conversation_agent.py's AI Foundry SDK AgentDefinition).

Checks whether a meeting-context draft has enough REAL context to proceed —
not just whether the required fields are filled in. readiness.py's
check_readiness() deliberately only checks presence (is a field non-empty);
its own docstring names this exact agent as the extension point for judging
sufficiency/clarity, which pure presence-checking code can't do (an
objective like "discuss business" passes every presence check while being
useless to the Deck Planner).

This is the agent served by app.py's AG-UI endpoint (the only one of the
four agents meant for direct chat interaction — Deck Planner, Content
Verifier and Brief are invoked programmatically from the deck-build
pipeline, never as a standalone chat agent).

Built with a checkpointer (in-memory — fine for this single-process dev/test
agent; swap for a durable one, e.g. Postgres, before a real multi-instance
deployment) because the AG-UI bridge (ag_ui_langgraph) keys conversation
state by `threadId` and calls `graph.aget_state(...)` to sync it — a graph
compiled with no checkpointer raises `ValueError("No checkpointer set")` the
moment a chat-ui message comes in. The other three agents here are invoked
directly via `.invoke()`, never through the AG-UI thread model, so they
don't need one.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

import storage
from llm import get_chat_model
from readiness import check_readiness

NAME = "Conversation Agent"
DESCRIPTION = (
    "Checks whether a sales rep's meeting-context draft has enough real context to "
    "proceed — not just whether the required fields are filled in, but whether "
    "what's there is specific and usable."
)

DOMAIN_PROMPT = (
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
)


@tool
def check_context_readiness(draft_id: str) -> dict:
    """The deterministic ground truth (which required fields are present,
    plus the actual text of the free-form ones) for one meeting-context
    draft. Judging whether that text is specific enough is the agent's job,
    not this function's — see readiness.py's docstring.

    Args:
        draft_id: the meeting-context draft to check.
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


def build_conversation_agent() -> CompiledStateGraph:
    """Builds a fresh compiled graph. Deliberately not built at import time —
    `get_chat_model()` resolves real Portkey credentials, and importing this
    module (e.g. for its tool/prompt) must never require them, matching this
    project's standing rule that defining an agent can't incur cost or need
    credentials; only building/invoking it can."""
    return create_agent(
        model=get_chat_model(),
        tools=[check_context_readiness],
        system_prompt=DOMAIN_PROMPT,
        name=NAME,
        checkpointer=InMemorySaver(),
    )
