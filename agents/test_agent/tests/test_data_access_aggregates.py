"""Tests for the numeric aggregation functions that feed the Builder."""

from data_access import (
    get_canonical_seasons_for_customer,
    get_product_metrics_by_season_for_customer,
    get_revenue_by_season_and_segment_for_customer,
    get_revenue_by_season_for_customer,
    get_segment_product_qty_by_season,
)

ACTURA_SEASONS = get_canonical_seasons_for_customer("ACTURA", n=3)


def test_canonical_seasons_most_recent_first() -> None:
    assert len(ACTURA_SEASONS) == 3
    assert ACTURA_SEASONS == sorted(ACTURA_SEASONS, reverse=True)


def test_revenue_by_season_returns_requested_seasons_exactly() -> None:
    result = get_revenue_by_season_for_customer("ACTURA", ACTURA_SEASONS)
    assert set(result) == set(ACTURA_SEASONS)
    assert all(isinstance(v, float) for v in result.values())


def test_product_metrics_sorted_by_total_revenue_descending() -> None:
    result = get_product_metrics_by_season_for_customer("ACTURA", ACTURA_SEASONS[:2])
    revenues = [sum(s["revenue"] for s in entry["by_season"].values()) for entry in result.values()]
    assert revenues == sorted(revenues, reverse=True)
    for entry in result.values():
        assert "unit" in entry
        assert set(entry["by_season"]) == set(ACTURA_SEASONS[:2])


def test_revenue_by_segment_sorted_descending() -> None:
    result = get_revenue_by_season_and_segment_for_customer("ACTURA", ACTURA_SEASONS)
    totals = [sum(v.values()) for v in result.values()]
    assert totals == sorted(totals, reverse=True)


def test_segment_product_qty_aligns_to_the_same_canonical_seasons_even_with_gaps() -> None:
    """Regression test for the season-misalignment bug: a customer+segment
    slice with sparse coverage must NOT get its seasons repositioned to look
    adjacent — missing seasons should show as 0.0 at their real position."""
    by_segment = get_revenue_by_season_and_segment_for_customer("ACTURA", ACTURA_SEASONS)
    top_segment = next(iter(by_segment))
    result = get_segment_product_qty_by_season("ACTURA", top_segment, ACTURA_SEASONS)
    assert result  # ACTURA's top segment should have at least one product
    for qty_by_season in result.values():
        # Every product entry carries all 3 canonical seasons as keys,
        # regardless of how much data that product+segment actually has —
        # missing ones are 0.0, not silently dropped/reindexed.
        assert set(qty_by_season) == set(ACTURA_SEASONS)
