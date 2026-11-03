"""Local-sample stand-in for a real Databricks query.

IMPORTANT — NOT representative of the real warehouse. Confirmed by the user
running the real queries against venus_gold_prod.cp_sales_overview.
cp_france_sales_insight on 2026-10-30: 11 distinct customers, 28 distinct
market segments, 820 distinct products — this sample only has 3 customers,
~18 segments, 69 products. Used only when data_access/databricks.py isn't
configured (see data_access/__init__.py's dispatch logic).
"""

from __future__ import annotations

import csv
from pathlib import Path

LOCAL_SAMPLE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "dbx-data" / "cp_france_sales_insight_100_records.csv"
)


def read_rows() -> list[dict[str, str]]:
    with LOCAL_SAMPLE_PATH.open(encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row.get("sys_delete_flag", "").lower() != "true"]


def to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def dedupe_seasons(rows: list[dict], season_key: str = "season", start_key: str = "season_start_date") -> list[str]:
    """One season label can appear with several distinct start dates (different
    product categories' sub-periods start on different dates within the same
    named season). Dedup on the label alone, using its earliest start date
    only to order seasons chronologically, most recent first. Shared by both
    the real and local paths since both hit the same underlying column shape.
    """
    earliest_start: dict[str, str] = {}
    for row in rows:
        season, start = row.get(season_key), row.get(start_key)
        if season and start and (season not in earliest_start or start < earliest_start[season]):
            earliest_start[season] = start
    return [s for s, _ in sorted(earliest_start.items(), key=lambda kv: kv[1], reverse=True)]


def get_distinct_customers() -> list[str]:
    rows = read_rows()
    return sorted({row["fr_main_account"] for row in rows if row.get("fr_main_account")})


def get_distinct_seasons() -> list[str]:
    return dedupe_seasons(read_rows())


def get_distinct_campaigns() -> list[str]:
    rows = read_rows()
    return sorted({row["campaign"] for row in rows if row.get("campaign")})


def get_distinct_products(customer: str | None = None) -> list[str]:
    rows = read_rows()
    if customer:
        rows = [row for row in rows if row.get("fr_main_account") == customer]
    return sorted({row["tradename_en"] for row in rows if row.get("tradename_en")})


def get_segments_and_products_by_customer(customer: str) -> dict[str, list[str]]:
    by_segment: dict[str, set[str]] = {}
    for row in read_rows():
        if row.get("fr_main_account") != customer:
            continue
        segment, product = row.get("france_sms_fr"), row.get("tradename_en")
        if segment and product:
            by_segment.setdefault(segment, set()).add(product)
    return {segment: sorted(products) for segment, products in sorted(by_segment.items())}


def get_canonical_seasons_for_customer(customer: str, n: int) -> list[str]:
    rows = [r for r in read_rows() if r.get("fr_main_account") == customer]
    return dedupe_seasons(rows)[:n]


def get_revenue_by_season_for_customer(customer: str, seasons: list[str]) -> dict[str, float]:
    totals = {s: 0.0 for s in seasons}
    rows = [r for r in read_rows() if r.get("fr_main_account") == customer]
    for row in rows:
        if row.get("season") in totals:
            totals[row["season"]] += to_float(row.get("customer_invoiced_value", "0"))
    return totals


def get_product_metrics_by_season_for_customer(customer: str, seasons: list[str]) -> dict[str, dict]:
    products: dict[str, dict] = {}

    def _add(product: str, unit: str, season: str, qty, revenue) -> None:
        entry = products.setdefault(
            product, {"unit": unit, "by_season": {s: {"qty": 0.0, "revenue": 0.0} for s in seasons}}
        )
        entry["by_season"][season]["qty"] += to_float(qty)
        entry["by_season"][season]["revenue"] += to_float(revenue)

    for row in read_rows():
        if row.get("fr_main_account") != customer:
            continue
        season = row.get("season")
        if season not in seasons or not row.get("tradename_en"):
            continue
        _add(
            row["tradename_en"],
            row.get("sales_uom", ""),
            season,
            row.get("customer_order_qty_suom", "0"),
            row.get("customer_invoiced_value", "0"),
        )

    ranked = sorted(products.items(), key=lambda kv: sum(s["revenue"] for s in kv[1]["by_season"].values()), reverse=True)
    return dict(ranked)


def get_revenue_by_season_and_segment_for_customer(customer: str, seasons: list[str]) -> dict[str, dict[str, float]]:
    segments: dict[str, dict[str, float]] = {}

    def _add(segment: str, season: str, revenue) -> None:
        entry = segments.setdefault(segment, {s: 0.0 for s in seasons})
        entry[season] += to_float(revenue)

    for row in read_rows():
        if row.get("fr_main_account") != customer:
            continue
        season = row.get("season")
        if season not in seasons or not row.get("france_sms_fr"):
            continue
        _add(row["france_sms_fr"], season, row.get("customer_invoiced_value", "0"))

    ranked = sorted(segments.items(), key=lambda kv: sum(kv[1].values()), reverse=True)
    return dict(ranked)


def get_segment_product_qty_by_season(customer: str, segment: str, seasons: list[str]) -> dict[str, dict[str, float]]:
    products: dict[str, dict[str, float]] = {}

    def _add(product: str, season: str, qty) -> None:
        entry = products.setdefault(product, {s: 0.0 for s in seasons})
        entry[season] += to_float(qty)

    rows = [r for r in read_rows() if r.get("fr_main_account") == customer and r.get("france_sms_fr") == segment]
    for row in rows:
        season = row.get("season")
        if season not in seasons or not row.get("tradename_en"):
            continue
        _add(row["tradename_en"], season, row.get("customer_order_qty_suom", "0"))

    ranked = sorted(products.items(), key=lambda kv: sum(kv[1].values()), reverse=True)
    return dict(ranked)
