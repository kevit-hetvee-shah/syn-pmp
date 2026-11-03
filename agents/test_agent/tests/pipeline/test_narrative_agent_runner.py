"""Tests for pipeline/narrative_agent_runner.py — the real Portkey/LLM call
boundary. Mocks build_agent directly (never relies on SKIP_NARRATIVE_AGENT,
which is a production/manual-testing escape hatch, not a test mechanism) so
these tests exercise the Pydantic-to-dataclass conversion and the
validate-before-trusting wiring with zero real network calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from pipeline.data_analyst import fetch_customer_facts
from pipeline.models import NarrativeCalloutBlock, NarrativeKpiBlock
from pipeline.narrative_agent_runner import (
    NarrativeAgentError,
    NarrativeSlideSpecModel,
    generate_narrative_slides,
    invoke_brief_agent,
)
from pipeline.narrative_facts import NARRATIVE_SLIDE_KEYS, compute_narrative_facts


def _mock_managed_agent(structured_output):
    result = MagicMock()
    result.structured_output = structured_output
    managed = MagicMock()
    managed.agent.return_value = result
    managed.__enter__.return_value = managed
    managed.__exit__.return_value = False
    return managed


def test_invoke_brief_agent_converts_and_validates_structured_output() -> None:
    facts = fetch_customer_facts("ACTURA")
    narrative = compute_narrative_facts("executive_summary", facts)
    model = NarrativeSlideSpecModel(
        slide_key="executive_summary",
        title="Executive Summary",
        blocks=[
            {
                "block_type": "kpi",
                "label": "Revenue",
                "value_fact_id": narrative.facts["revenue_curr_fact_id"],
                "delta_from_fact_id": narrative.facts["revenue_prev_fact_id"],
            }
        ],
    )
    managed = _mock_managed_agent(model)

    with patch("pipeline.narrative_agent_runner.build_agent", return_value=managed) as mock_build_agent:
        spec = invoke_brief_agent(facts, "executive_summary")

    mock_build_agent.assert_called_once()
    managed.agent.assert_called_once()
    assert spec.slide_key == "executive_summary"
    assert isinstance(spec.blocks[0], NarrativeKpiBlock)
    assert spec.blocks[0].value_fact_id == narrative.facts["revenue_curr_fact_id"]


def test_invoke_brief_agent_raises_on_missing_structured_output() -> None:
    facts = fetch_customer_facts("ACTURA")
    managed = _mock_managed_agent(None)
    with patch("pipeline.narrative_agent_runner.build_agent", return_value=managed):
        with pytest.raises(NarrativeAgentError, match="no structured output"):
            invoke_brief_agent(facts, "executive_summary")


def test_invoke_brief_agent_raises_on_fact_id_the_agent_was_not_given() -> None:
    facts = fetch_customer_facts("ACTURA")
    model = NarrativeSlideSpecModel(
        slide_key="executive_summary",
        title="Executive Summary",
        blocks=[{"block_type": "callout", "text": "Made up.", "cited_fact_ids": ["f9999"]}],
    )
    managed = _mock_managed_agent(model)
    with patch("pipeline.narrative_agent_runner.build_agent", return_value=managed):
        with pytest.raises(NarrativeAgentError, match="invalid slide spec"):
            invoke_brief_agent(facts, "executive_summary")


def test_generate_narrative_slides_skips_the_real_call_when_flagged(monkeypatch) -> None:
    monkeypatch.setenv("SKIP_NARRATIVE_AGENT", "true")
    facts = fetch_customer_facts("ACTURA")
    with patch("pipeline.narrative_agent_runner.build_agent") as mock_build_agent:
        slides = generate_narrative_slides(facts)
    mock_build_agent.assert_not_called()
    assert set(slides.keys()) == set(NARRATIVE_SLIDE_KEYS)
    for spec in slides.values():
        assert isinstance(spec.blocks[0], NarrativeCalloutBlock)


def test_generate_narrative_slides_calls_the_agent_once_per_slide_when_not_skipped(monkeypatch) -> None:
    monkeypatch.setenv("SKIP_NARRATIVE_AGENT", "false")
    facts = fetch_customer_facts("ACTURA")
    model = NarrativeSlideSpecModel(
        slide_key="x",
        title="x",
        blocks=[{"block_type": "callout", "text": "Not groundable yet.", "cited_fact_ids": []}],
    )
    managed = _mock_managed_agent(model)
    with patch("pipeline.narrative_agent_runner.build_agent", return_value=managed) as mock_build_agent:
        slides = generate_narrative_slides(facts)
    assert mock_build_agent.call_count == len(NARRATIVE_SLIDE_KEYS)
    assert set(slides.keys()) == set(NARRATIVE_SLIDE_KEYS)
