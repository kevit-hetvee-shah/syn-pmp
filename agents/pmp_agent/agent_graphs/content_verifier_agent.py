"""Content Verifier Agent — LangGraph version (replaces agent_definitions/
content_verifier_agent.py's AI Foundry SDK AgentDefinition).

Reviews a generated deck beyond what the deterministic checks can judge.
pipeline.validator.validate_deck_spec (before rendering) and
pipeline.renderer.post_render_check (after rendering) are rule-based: they
confirm every number traces to a real fetched fact, and that the rendered
file matches the spec that produced it. Neither can judge anything that
needs actual understanding — does a number look implausible even though
it's technically fact-backed, does the slide count make sense for this
client's data volume, is there anything a rep should double-check before a
customer meeting. That's this agent's job, layered on top of — never
instead of — the deterministic checks.

Not invoked anywhere by default, same as the old agent_definitions module.
Importing this module never needs credentials; building the agent
(build_content_verifier_agent()) does — see conversation_agent.py's
docstring for the full reasoning.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph

from llm import get_chat_model
from pipeline.diagnostics import check_deck as _check_deck

NAME = "Content Verifier Agent"
DESCRIPTION = (
    "Reviews a generated client-facing deck beyond what deterministic rule-checks can "
    "judge — plausibility, coherence, and whether the deck's shape makes sense for this "
    "meeting."
)

DOMAIN_PROMPT = (
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
)


@tool
def check_deck(customer: str, meeting_date: str) -> dict:
    """Runs the full deck-build pipeline for one customer and reports the
    outcome of every stage, without raising — the deterministic ground truth
    this agent's own plausibility judgment builds on.

    Args:
        customer: the customer to build and check a deck for.
        meeting_date: the meeting date to stamp the deck's cover with.
    """
    return _check_deck(customer, meeting_date)


def build_content_verifier_agent() -> CompiledStateGraph:
    return create_agent(
        model=get_chat_model(),
        tools=[check_deck],
        system_prompt=DOMAIN_PROMPT,
        name=NAME,
    )
