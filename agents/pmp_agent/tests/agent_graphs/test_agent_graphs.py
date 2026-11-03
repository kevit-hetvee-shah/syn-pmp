"""Construction-only tests for every agent_graphs/*.py agent — each must
build into a real compiled LangGraph graph with placeholder credentials
(tests/conftest.py), with zero network calls. Invocation (an actual model
call) is deliberately never exercised in this test suite — see
tests/pipeline/test_narrative_agent_runner.py for the one agent that's
invoked for real in production, tested there via a fully mocked graph.
"""

from langgraph.graph.state import CompiledStateGraph

from agent_graphs.brief_agent import build_brief_agent
from agent_graphs.content_verifier_agent import build_content_verifier_agent
from agent_graphs.conversation_agent import build_conversation_agent
from agent_graphs.deck_planner_agent import build_deck_planner_agent
from pipeline.data_analyst import fetch_customer_facts


def test_conversation_agent_builds() -> None:
    assert isinstance(build_conversation_agent(), CompiledStateGraph)


def test_deck_planner_agent_builds() -> None:
    assert isinstance(build_deck_planner_agent(), CompiledStateGraph)


def test_content_verifier_agent_builds() -> None:
    assert isinstance(build_content_verifier_agent(), CompiledStateGraph)


def test_brief_agent_builds_bound_to_one_build_s_facts() -> None:
    facts = fetch_customer_facts("ACTURA")
    graph = build_brief_agent(facts)
    assert isinstance(graph, CompiledStateGraph)

    # A fresh build for the same customer gets its own graph/tool closure —
    # never a shared/cached instance, since each deck build's facts/registry
    # must stay isolated (see agent_graphs/brief_agent.py's docstring).
    other_graph = build_brief_agent(fetch_customer_facts("ACTURA"))
    assert graph is not other_graph
