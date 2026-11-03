"""Tests for the Narrative Analyst (pipeline/narrative_facts.py) — pure
deterministic logic, no SDK/agent involved.
"""

from pipeline.data_analyst import fetch_customer_facts
from pipeline.narrative_facts import NOT_GROUNDABLE, compute_narrative_facts


def test_market_benchmarking_and_operational_risk_are_explicitly_not_groundable() -> None:
    facts = fetch_customer_facts("ACTURA")
    for slide_key in ("market_benchmarking", "operational_risk"):
        narrative = compute_narrative_facts(slide_key, facts)
        assert narrative.groundable is False
        assert narrative.reason_not_groundable == NOT_GROUNDABLE[slide_key]
        assert narrative.facts == {}


def test_executive_summary_registers_a_revenue_delta_and_trajectory_label() -> None:
    facts = fetch_customer_facts("ACTURA")
    narrative = compute_narrative_facts("executive_summary", facts)
    assert narrative.groundable is True

    delta_fid = narrative.facts["revenue_delta_fact_id"]
    prev_fid = narrative.facts["revenue_prev_fact_id"]
    curr_fid = narrative.facts["revenue_curr_fact_id"]
    delta = facts.registry.get(delta_fid)
    prev = facts.registry.get(prev_fid)
    curr = facts.registry.get(curr_fid)
    assert delta.value == curr.value - prev.value
    assert delta.source_template == "computed_delta"
    assert delta.source_params == {"from_fact_id": prev_fid, "to_fact_id": curr_fid}

    trajectory = facts.registry.get(narrative.facts["revenue_trajectory_fact_id"])
    assert trajectory.value in ("growing", "shrinking", "flat", "new")


def test_executive_summary_biggest_win_and_risk_are_real_opposite_ranked_products() -> None:
    facts = fetch_customer_facts("ACTURA")
    narrative = compute_narrative_facts("executive_summary", facts)
    assert "biggest_win_delta_fact_id" in narrative.facts
    assert "biggest_risk_delta_fact_id" in narrative.facts

    win_delta = float(facts.registry.get(narrative.facts["biggest_win_delta_fact_id"]).value)
    risk_delta = float(facts.registry.get(narrative.facts["biggest_risk_delta_fact_id"]).value)
    assert win_delta >= risk_delta  # the ranking is real, not coincidental equal picks


def test_account_health_flags_volume_ambiguity_as_a_caveat_instead_of_computing_one() -> None:
    facts = fetch_customer_facts("ACTURA")
    narrative = compute_narrative_facts("account_health", facts)
    assert narrative.groundable is True
    assert not any("volume_fact_id" == key or "volume_delta" in key for key in narrative.facts)
    assert any("unit" in caveat.lower() and "volume" in caveat.lower() for caveat in narrative.caveats)


def test_account_health_identifies_a_real_best_season() -> None:
    facts = fetch_customer_facts("ACTURA")
    narrative = compute_narrative_facts("account_health", facts)
    best_fid = narrative.facts["best_season_revenue_fact_id"]
    best_value = float(facts.registry.get(best_fid).value)
    all_season_values = [
        float(facts.registry.get(fid).value) for key, fid in narrative.facts.items() if key.startswith("revenue_") and key.endswith("_fact_id") and "best" not in key and "delta" not in key and "prev" not in key and "curr" not in key
    ]
    assert best_value == max(all_season_values)


def test_portfolio_shifts_ranks_winners_above_bleeders_by_revenue_delta() -> None:
    facts = fetch_customer_facts("ACTURA")
    narrative = compute_narrative_facts("portfolio_shifts", facts)
    assert narrative.groundable is True
    assert "winner_1_delta_fact_id" in narrative.facts

    winner_delta = float(facts.registry.get(narrative.facts["winner_1_delta_fact_id"]).value)
    if "bleeder_1_delta_fact_id" in narrative.facts:
        bleeder_delta = float(facts.registry.get(narrative.facts["bleeder_1_delta_fact_id"]).value)
        assert winner_delta >= bleeder_delta


def test_portfolio_shifts_flags_premium_commodity_gap_as_a_caveat() -> None:
    facts = fetch_customer_facts("ACTURA")
    narrative = compute_narrative_facts("portfolio_shifts", facts)
    assert any("premium" in caveat.lower() and "commodity" in caveat.lower() for caveat in narrative.caveats)
