"""Tests for the local-sample data-access stand-in (not a real Databricks call)."""

from data_access import (
    get_distinct_campaigns,
    get_distinct_customers,
    get_distinct_products,
    get_distinct_seasons,
    get_segments_and_products_by_customer,
)


def test_distinct_customers_matches_known_sample_accounts() -> None:
    customers = get_distinct_customers()
    assert "ACTURA" in customers
    assert "SYMPHONIE" in customers
    assert customers == sorted(customers)


def test_distinct_seasons_sorted_most_recent_first() -> None:
    seasons = get_distinct_seasons()
    assert seasons[0] > seasons[-1]  # "2025/2026" > "2016/2017" lexically too
    assert "2025/2026" in seasons


def test_distinct_campaigns_are_not_season_values() -> None:
    """Regression test: Campaign was a separate bug where the UI's Campaign
    dropdown was reusing get_distinct_seasons()'s output. campaign (e.g.
    "F03") is a genuinely different column from season (e.g. "2025/2026")."""
    campaigns = get_distinct_campaigns()
    seasons = get_distinct_seasons()
    assert campaigns, "sample should have real campaign values"
    assert set(campaigns).isdisjoint(set(seasons))
    assert all(c.startswith("F") for c in campaigns)  # matches the sample's F01..F07 pattern


def test_distinct_products_can_be_scoped_to_a_customer() -> None:
    all_products = get_distinct_products()
    actura_products = get_distinct_products(customer="ACTURA")
    assert len(actura_products) < len(all_products)
    assert set(actura_products).issubset(set(all_products))


def test_segments_and_products_by_customer_shape() -> None:
    result = get_segments_and_products_by_customer("ACTURA")
    assert isinstance(result, dict)
    assert all(isinstance(products, list) and products for products in result.values())
