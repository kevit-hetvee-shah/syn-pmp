"""Data Analyst step: fetch real data for one customer, record every value
as a Fact. Always deterministic — this is the trust boundary an LLM never
crosses; every number that ends up in a deck traces back to a row created
here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import data_access
from pipeline.models import FactRegistry


@dataclass
class ProductFacts:
    name: str
    name_fact_id: str
    unit: str
    by_season: dict[str, dict[str, str]]  # season -> {"qty_fact_id": ..., "revenue_fact_id": ...}


@dataclass
class SegmentFacts:
    name: str
    name_fact_id: str
    by_season: dict[str, str]  # season -> revenue fact_id


@dataclass
class CustomerFacts:
    registry: FactRegistry
    customer: str
    seasons: list[str]  # canonical N-2/N-1/N labels, most recent first
    revenue_by_season_fact_ids: dict[str, str]  # season -> fact_id
    products: list[ProductFacts]  # ranked by revenue, descending
    segments: list[SegmentFacts]  # ranked by revenue, descending
    top_segment_products: dict[str, list[ProductFacts]] = field(default_factory=dict)  # segment_name -> ranked products


def fetch_customer_facts(customer: str, n_seasons: int = 3) -> CustomerFacts:
    registry = FactRegistry()
    seasons = data_access.get_canonical_seasons_for_customer(customer, n=n_seasons)

    revenue_by_season = data_access.get_revenue_by_season_for_customer(customer, seasons)
    revenue_fact_ids = {
        season: registry.add(
            label=f"{customer} revenue, {season}",
            value=value,
            unit="EUR",
            source_template="revenue_by_season_for_customer",
            source_params={"customer": customer, "season": season},
        )
        for season, value in revenue_by_season.items()
    }

    # Slide 4's template only has N-1/N columns (2 seasons).
    product_seasons = seasons[:2]
    product_metrics = data_access.get_product_metrics_by_season_for_customer(customer, product_seasons)
    products = [
        _product_facts(registry, customer, name, entry, product_seasons, "product_metrics_by_season_for_customer")
        for name, entry in product_metrics.items()
    ]

    by_segment = data_access.get_revenue_by_season_and_segment_for_customer(customer, seasons)
    segments: list[SegmentFacts] = []
    for name, by_season_values in by_segment.items():
        by_season_fact_ids = {
            season: registry.add(
                label=f"{name} revenue, {season}",
                value=value,
                unit="EUR",
                source_template="revenue_by_season_and_segment_for_customer",
                source_params={"customer": customer, "segment": name, "season": season},
            )
            for season, value in by_season_values.items()
        }
        name_fid = registry.add(
            label="Segment name",
            value=name,
            source_template="revenue_by_season_and_segment_for_customer",
            source_params={"customer": customer, "segment": name},
        )
        segments.append(SegmentFacts(name=name, name_fact_id=name_fid, by_season=by_season_fact_ids))

    # Deep-dive: the top segment's own products, by quantity.
    top_segment_products: dict[str, list[ProductFacts]] = {}
    if segments:
        top_segment_name = segments[0].name
        qty_by_product = data_access.get_segment_product_qty_by_season(customer, top_segment_name, seasons)
        top_segment_products[top_segment_name] = [
            _deepdive_product_facts(registry, customer, top_segment_name, name, by_season_values, seasons)
            for name, by_season_values in qty_by_product.items()
        ]

    return CustomerFacts(
        registry=registry,
        customer=customer,
        seasons=seasons,
        revenue_by_season_fact_ids=revenue_fact_ids,
        products=products,
        segments=segments,
        top_segment_products=top_segment_products,
    )


def _product_facts(
    registry: FactRegistry, customer: str, name: str, entry: dict, seasons: list[str], source_template: str
) -> ProductFacts:
    by_season: dict[str, dict[str, str]] = {}
    for season in seasons:
        qty = entry["by_season"][season]["qty"]
        revenue = entry["by_season"][season]["revenue"]
        qty_fid = registry.add(
            label=f"{name} qty, {season}",
            value=qty,
            unit=entry["unit"],
            source_template=source_template,
            source_params={"customer": customer, "product": name, "season": season},
        )
        revenue_fid = registry.add(
            label=f"{name} revenue, {season}",
            value=revenue,
            unit="EUR",
            source_template=source_template,
            source_params={"customer": customer, "product": name, "season": season},
        )
        by_season[season] = {"qty_fact_id": qty_fid, "revenue_fact_id": revenue_fid}
    name_fid = registry.add(
        label="Product name", value=name, source_template=source_template, source_params={"customer": customer, "product": name}
    )
    return ProductFacts(name=name, name_fact_id=name_fid, unit=entry["unit"], by_season=by_season)


def _deepdive_product_facts(
    registry: FactRegistry, customer: str, segment: str, name: str, by_season_values: dict[str, float], seasons: list[str]
) -> ProductFacts:
    by_season: dict[str, dict[str, str]] = {}
    for season in seasons:
        qty_fid = registry.add(
            label=f"{name} qty, {season} ({segment})",
            value=by_season_values[season],
            source_template="segment_product_qty_by_season",
            source_params={"customer": customer, "segment": segment, "product": name, "season": season},
        )
        by_season[season] = {"qty_fact_id": qty_fid}
    name_fid = registry.add(
        label="Product name",
        value=name,
        source_template="segment_product_qty_by_season",
        source_params={"customer": customer, "segment": segment, "product": name},
    )
    return ProductFacts(name=name, name_fact_id=name_fid, unit="", by_season=by_season)
