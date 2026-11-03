"""Data access for the SQL templates in utils/sql_registry.py — real
Databricks when configured, a local-sample stand-in otherwise.

Per the user (2026-10-31): customer / season / product lists should be
DB-backed for real, not just mock lists — data_access/databricks.py does
that when `PM_DATABRICKS_HOST` / `PM_DATABRICKS_TOKEN` / `PM_DATABRICKS_CATALOG`
/ `PM_DATABRICKS_SCHEMA` are configured (see that module's docstring for the
caveat that this runs as a real workspace PAT token, not the platform's
sanctioned per-rep MCP-Gateway path). Without those env vars, every function
below falls back to data_access/local_csv.py, clearly flagged as NOT
representative of the real warehouse (11 customers/28 segments/820 products
vs. the sample's 3/~18/69 — see project memory).

Every public function here corresponds 1:1 to a sql_registry.py template —
that correspondence is what makes "where did this number come from"
traceable, matching the DeckSmith provenance pattern this project follows.
`current_data_source()` reports which path is actually active, so the UI/API
can show it (never silently pretend local-sample data is live).

This module is the dispatch layer only — the two implementations
(data_access.databricks, data_access.local_csv) hold the actual logic, kept
in sync 1:1 by `pipeline/data_analyst.py`'s callers using these same
function names regardless of which backend answered.
"""

from __future__ import annotations

from data_access import databricks, local_csv


def current_data_source() -> str:
    return "databricks" if databricks.is_configured() else "local-sample-csv"


def get_distinct_customers() -> list[str]:
    """Backs sql_registry template 'distinct_customers'."""
    if databricks.is_configured():
        rows = databricks.execute_template("distinct_customers")
        return sorted({r["client"] for r in rows if r.get("client")})
    return local_csv.get_distinct_customers()


def get_distinct_seasons() -> list[str]:
    """Backs sql_registry template 'distinct_seasons'."""
    if databricks.is_configured():
        rows = databricks.execute_template("distinct_seasons")
        return local_csv.dedupe_seasons(rows)
    return local_csv.get_distinct_seasons()


def get_distinct_campaigns() -> list[str]:
    """Backs sql_registry template 'distinct_campaigns'.

    Campaign (e.g. "F03") is a genuinely separate dimension from season
    (e.g. "2025/2026") — confirmed against the real `campaign` column, not
    derived from `season`/`season_start_date`. Fixes a bug where the UI's
    Campaign dropdown was reusing the seasons list.
    """
    if databricks.is_configured():
        rows = databricks.execute_template("distinct_campaigns")
        return sorted({r["campaign"] for r in rows if r.get("campaign")})
    return local_csv.get_distinct_campaigns()


def get_distinct_products(customer: str | None = None) -> list[str]:
    """Backs sql_registry template 'distinct_products'."""
    if databricks.is_configured():
        rows = databricks.execute_template("distinct_products", customer=customer)
        return sorted({r["product"] for r in rows if r.get("product")})
    return local_csv.get_distinct_products(customer)


def get_segments_and_products_by_customer(customer: str) -> dict[str, list[str]]:
    """Backs sql_registry template 'segments_and_products_by_customer'.

    Returns {segment: [products...]} — feeds deck_plan.compute_slide_plan's
    total_market_segments / segment_product_counts inputs.
    """
    if not databricks.is_configured():
        return local_csv.get_segments_and_products_by_customer(customer)
    by_segment: dict[str, set[str]] = {}
    rows = databricks.execute_template("segments_and_products_by_customer", customer=customer)
    for row in rows:
        segment, product = row.get("segment"), row.get("product")
        if segment and product:
            by_segment.setdefault(segment, set()).add(product)
    return {segment: sorted(products) for segment, products in sorted(by_segment.items())}


def get_canonical_seasons_for_customer(customer: str, n: int) -> list[str]:
    """The N-2/N-1/N season labels for a customer, most recent first.

    Computed ONCE from ALL of that customer's rows (not a narrower
    product/segment slice) so every slide/metric for this customer aligns to
    the same N-2/N-1/N columns — a past bug had each aggregation
    independently guessing "most recent N seasons" from its own narrower
    slice, which could misalign when that slice had sparse coverage.
    """
    if databricks.is_configured():
        rows = databricks.execute_template("revenue_by_season_for_customer", customer=customer)
        return local_csv.dedupe_seasons(rows)[:n]
    return local_csv.get_canonical_seasons_for_customer(customer, n)


def get_revenue_by_season_for_customer(customer: str, seasons: list[str]) -> dict[str, float]:
    """Backs sql_registry template 'revenue_by_season_for_customer'. Returns {season: revenue} for exactly `seasons`."""
    if not databricks.is_configured():
        return local_csv.get_revenue_by_season_for_customer(customer, seasons)
    totals = {s: 0.0 for s in seasons}
    rows = databricks.execute_template("revenue_by_season_for_customer", customer=customer)
    for row in rows:
        if row.get("season") in totals:
            totals[row["season"]] += local_csv.to_float(row.get("revenue"))
    return totals


def get_product_metrics_by_season_for_customer(customer: str, seasons: list[str]) -> dict[str, dict]:
    """Backs sql_registry template 'product_metrics_by_season_for_customer'.

    Returns {product: {"unit": str, "by_season": {season: {"qty": float, "revenue": float}}}}
    for exactly `seasons` (missing data for a season stays 0.0, not dropped/shifted), sorted by
    total revenue descending.
    """
    if not databricks.is_configured():
        return local_csv.get_product_metrics_by_season_for_customer(customer, seasons)

    products: dict[str, dict] = {}
    rows = databricks.execute_template("product_metrics_by_season_for_customer", customer=customer)
    for row in rows:
        season = row.get("season")
        if season not in seasons or not row.get("product"):
            continue
        entry = products.setdefault(
            row["product"], {"unit": row.get("unit", ""), "by_season": {s: {"qty": 0.0, "revenue": 0.0} for s in seasons}}
        )
        entry["by_season"][season]["qty"] += local_csv.to_float(row.get("qty"))
        entry["by_season"][season]["revenue"] += local_csv.to_float(row.get("revenue"))

    ranked = sorted(products.items(), key=lambda kv: sum(s["revenue"] for s in kv[1]["by_season"].values()), reverse=True)
    return dict(ranked)


def get_revenue_by_season_and_segment_for_customer(customer: str, seasons: list[str]) -> dict[str, dict[str, float]]:
    """Backs sql_registry template 'revenue_by_season_and_segment_for_customer'.

    Returns {segment: {season: revenue}} for exactly `seasons`, sorted by total revenue descending.
    """
    if not databricks.is_configured():
        return local_csv.get_revenue_by_season_and_segment_for_customer(customer, seasons)

    segments: dict[str, dict[str, float]] = {}
    rows = databricks.execute_template("revenue_by_season_and_segment_for_customer", customer=customer)
    for row in rows:
        season = row.get("season")
        if season not in seasons or not row.get("segment"):
            continue
        entry = segments.setdefault(row["segment"], {s: 0.0 for s in seasons})
        entry[season] += local_csv.to_float(row.get("revenue"))

    ranked = sorted(segments.items(), key=lambda kv: sum(kv[1].values()), reverse=True)
    return dict(ranked)


def get_segment_product_qty_by_season(customer: str, segment: str, seasons: list[str]) -> dict[str, dict[str, float]]:
    """Backs sql_registry template 'segment_product_qty_by_season'.

    Returns {product: {season: qty}} for exactly `seasons`, sorted by total qty descending.
    """
    if not databricks.is_configured():
        return local_csv.get_segment_product_qty_by_season(customer, segment, seasons)

    products: dict[str, dict[str, float]] = {}
    rows = databricks.execute_template("segment_product_qty_by_season", customer=customer, segment=segment)
    for row in rows:
        season = row.get("season")
        if season not in seasons or not row.get("product"):
            continue
        entry = products.setdefault(row["product"], {s: 0.0 for s in seasons})
        entry[season] += local_csv.to_float(row.get("qty"))

    ranked = sorted(products.items(), key=lambda kv: sum(kv[1].values()), reverse=True)
    return dict(ranked)


def get_customer_location(customer: str) -> str | None:
    """The customer account's State, used to auto-fill the read-only
    Location field on the Meeting Context screen ("Set the Region" story,
    2026-11-02). Unlike every other function here, this has NO backing
    sql_registry.py template yet, by necessity rather than oversight:
    neither the live Databricks table (venus_gold_prod.cp_sales_overview.
    cp_france_sales_insight — checked directly via DESCRIBE TABLE) nor the
    local CSV sample has a State/region column for a customer account; the
    closest real columns are account_city/account_country, not a "State".
    Returns None until a real source (e.g. a Salesforce Account.State field)
    is connected — deliberately not approximated from account_city, per the
    user (2026-11-02): "keep empty for now" rather than show a wrong value.
    """
    return None
