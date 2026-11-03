"""Tests for the SQL template registry — parsing and validation only, no execution."""

import pytest

from utils.sql_registry import TEMPLATES, get_template


def test_all_template_files_loaded() -> None:
    assert set(TEMPLATES) == {
        "distinct_customers",
        "distinct_customers_for_sales_rep",
        "location_for_customer",
        "distinct_seasons",
        "distinct_campaigns",
        "distinct_products",
        "segments_and_products_by_customer",
        "revenue_by_season_for_customer",
        "product_metrics_by_season_for_customer",
        "revenue_by_season_and_segment_for_customer",
        "segment_product_qty_by_season",
    }


def test_distinct_customers_has_no_params() -> None:
    template = get_template("distinct_customers")
    assert template.params == []
    assert "venus_gold_prod.cp_sales_overview.cp_france_sales_insight" in template.sql
    assert template.validate_params({}) == []


def test_distinct_products_customer_param_is_optional() -> None:
    template = get_template("distinct_products")
    assert len(template.params) == 1
    param = template.params[0]
    assert param.name == "customer"
    assert param.optional is True
    assert template.validate_params({}) == []  # omitting an optional param is fine
    assert template.validate_params({"customer": "ACTURA"}) == []


def test_distinct_customers_for_sales_rep_requires_owner_id() -> None:
    template = get_template("distinct_customers_for_sales_rep")
    assert len(template.params) == 1
    param = template.params[0]
    assert param.name == "owner_id"
    assert param.optional is False
    assert template.validate_params({}) == ["param 'owner_id' is required"]
    assert template.validate_params({"owner_id": "0053V000003KfbBQAS"}) == []
    assert template.validate_params({"owner_id": "not an id!"}) != []


def test_location_for_customer_requires_customer() -> None:
    template = get_template("location_for_customer")
    assert len(template.params) == 1
    param = template.params[0]
    assert param.name == "customer"
    assert param.optional is False
    assert "account_city" in template.sql
    assert template.validate_params({}) == ["param 'customer' is required"]
    assert template.validate_params({"customer": "ACTURA"}) == []


def test_segments_by_customer_requires_customer() -> None:
    template = get_template("segments_and_products_by_customer")
    errors = template.validate_params({})
    assert errors == ["param 'customer' is required"]
    assert template.validate_params({"customer": "ACTURA"}) == []


def test_unknown_param_is_rejected() -> None:
    template = get_template("distinct_customers")
    errors = template.validate_params({"not_a_real_param": "x"})
    assert "unknown param 'not_a_real_param'" in errors[0]


def test_unknown_template_id_raises() -> None:
    with pytest.raises(KeyError):
        get_template("does_not_exist")


def test_render_inlines_params_for_audit_display() -> None:
    template = get_template("segments_and_products_by_customer")
    rendered = template.render({"customer": "ACTURA"})
    assert "'ACTURA'" in rendered
    assert ":customer" not in rendered


def test_render_rejects_invalid_params() -> None:
    template = get_template("segments_and_products_by_customer")
    with pytest.raises(ValueError, match="required"):
        template.render({})


def test_executable_sql_resolves_table_but_keeps_param_placeholders() -> None:
    """executable_sql is for the real driver: {{table:...}} resolved (safe —
    reviewed template content, not user input), but :param placeholders left
    intact for the driver's own server-side binding (never inlined — that
    would reopen the injection risk render() exists to avoid for display)."""
    template = get_template("segments_and_products_by_customer")
    sql = template.executable_sql
    assert "{{table:" not in sql
    assert "venus_gold_prod.cp_sales_overview.cp_france_sales_insight" in sql
    assert ":customer" in sql
