"""Narrative Analyst: computes the DERIVED facts (deltas, rankings,
trajectory labels) the Brief Agent needs for the 5 "LLM Generated" slides —
still deterministic, still fact-registered, same trust boundary as
data_analyst.py. A derived fact's source_template is "computed_delta" or
"computed_label" instead of a SQL template name, and its source_params
point at the raw fact_id(s) it was computed from — the provenance chain
just gets one hop longer, it never breaks.

Two of the five slides (market_benchmarking, operational_risk) can't be
honestly grounded with the data this pipeline currently fetches — see
NOT_GROUNDABLE below. compute_narrative_facts() says so explicitly rather
than fabricating a plausible-looking number; a slide marked not-groundable
must stay out of the generated deck (or stay static) until real data backs
it, per the 2026-10-30 ideation on this template's "LLM Generated" slides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pipeline.data_analyst import CustomerFacts, ProductFacts
from pipeline.models import FactRegistry

NARRATIVE_SLIDE_KEYS = (
    "executive_summary",
    "account_health",
    "portfolio_shifts",
    "market_benchmarking",
    "operational_risk",
)

NOT_GROUNDABLE: dict[str, str] = {
    "market_benchmarking": (
        "Requires a regional/national average revenue-growth benchmark across ALL customers — "
        "fetch_customer_facts is single-customer scoped, and it's unconfirmed whether the real "
        "table even has a region/territory field to group by."
    ),
    "operational_risk": (
        "Requires order-fulfillment data (open orders, delivery-date status, unfulfilled quantities) — "
        "the sales-insight table is revenue/quantity by season, not order-level logistics. No field in "
        "the current schema maps to this at all."
    ),
}


@dataclass
class NarrativeFacts:
    slide_key: str
    groundable: bool
    facts: dict[str, str] = field(default_factory=dict)  # named slot -> fact_id
    caveats: list[str] = field(default_factory=list)  # things the Brief Agent must NOT claim/compute itself
    reason_not_groundable: Optional[str] = None


def compute_narrative_facts(slide_key: str, customer_facts: CustomerFacts) -> NarrativeFacts:
    if slide_key in NOT_GROUNDABLE:
        return NarrativeFacts(slide_key=slide_key, groundable=False, reason_not_groundable=NOT_GROUNDABLE[slide_key])
    if slide_key == "executive_summary":
        return _executive_summary_facts(customer_facts)
    if slide_key == "account_health":
        return _account_health_facts(customer_facts)
    if slide_key == "portfolio_shifts":
        return _portfolio_shifts_facts(customer_facts)
    raise ValueError(f"unknown narrative slide_key: {slide_key!r} (expected one of {NARRATIVE_SLIDE_KEYS})")


def _register_delta(registry: FactRegistry, label: str, from_fid: str, to_fid: str) -> str:
    from_value = float(registry.get(from_fid).value)
    to_value = float(registry.get(to_fid).value)
    return registry.add(
        label=label,
        value=to_value - from_value,
        unit=registry.get(to_fid).unit,
        source_template="computed_delta",
        source_params={"from_fact_id": from_fid, "to_fact_id": to_fid},
    )


def _trajectory_label(delta: float, from_value: float) -> str:
    if from_value == 0:
        return "new" if delta > 0 else "flat"
    change_ratio = delta / from_value
    if change_ratio > 0.03:
        return "growing"
    if change_ratio < -0.03:
        return "shrinking"
    return "flat"


def _latest_two_seasons(customer_facts: CustomerFacts) -> tuple[str, str]:
    """(previous, current) — CustomerFacts.seasons is most-recent-first."""
    return customer_facts.seasons[1], customer_facts.seasons[0]


def _product_revenue_delta(registry: FactRegistry, product: ProductFacts, prev_season: str, curr_season: str) -> Optional[str]:
    if prev_season not in product.by_season or curr_season not in product.by_season:
        return None
    return _register_delta(
        registry,
        label=f"{product.name} revenue change, {prev_season}→{curr_season}",
        from_fid=product.by_season[prev_season]["revenue_fact_id"],
        to_fid=product.by_season[curr_season]["revenue_fact_id"],
    )


def _executive_summary_facts(customer_facts: CustomerFacts) -> NarrativeFacts:
    registry = customer_facts.registry
    prev_season, curr_season = _latest_two_seasons(customer_facts)
    revenue_delta_fid = _register_delta(
        registry,
        label=f"{customer_facts.customer} revenue change, {prev_season}→{curr_season}",
        from_fid=customer_facts.revenue_by_season_fact_ids[prev_season],
        to_fid=customer_facts.revenue_by_season_fact_ids[curr_season],
    )
    prev_value = float(registry.get(customer_facts.revenue_by_season_fact_ids[prev_season]).value)
    delta_value = float(registry.get(revenue_delta_fid).value)
    trajectory_fid = registry.add(
        label=f"{customer_facts.customer} revenue trajectory",
        value=_trajectory_label(delta_value, prev_value),
        source_template="computed_label",
        source_params={"based_on_fact_id": revenue_delta_fid},
    )

    deltas = [
        (product, _product_revenue_delta(registry, product, prev_season, curr_season)) for product in customer_facts.products
    ]
    deltas = [(p, fid) for p, fid in deltas if fid is not None]
    facts: dict[str, str] = {
        "revenue_prev_fact_id": customer_facts.revenue_by_season_fact_ids[prev_season],
        "revenue_curr_fact_id": customer_facts.revenue_by_season_fact_ids[curr_season],
        "revenue_delta_fact_id": revenue_delta_fid,
        "revenue_trajectory_fact_id": trajectory_fid,
    }
    if deltas:
        biggest_win = max(deltas, key=lambda pair: float(registry.get(pair[1]).value))
        biggest_risk = min(deltas, key=lambda pair: float(registry.get(pair[1]).value))
        facts["biggest_win_name_fact_id"] = biggest_win[0].name_fact_id
        facts["biggest_win_delta_fact_id"] = biggest_win[1]
        facts["biggest_risk_name_fact_id"] = biggest_risk[0].name_fact_id
        facts["biggest_risk_delta_fact_id"] = biggest_risk[1]

    return NarrativeFacts(
        slide_key="executive_summary",
        groundable=True,
        facts=facts,
        caveats=[
            "The strategic recommendation is your own judgment call, grounded in the facts above — "
            "it is not itself a fact, do not present it as a measured value.",
        ],
    )


def _account_health_facts(customer_facts: CustomerFacts) -> NarrativeFacts:
    registry = customer_facts.registry
    prev_season, curr_season = _latest_two_seasons(customer_facts)
    revenue_delta_fid = _register_delta(
        registry,
        label=f"{customer_facts.customer} revenue change, {prev_season}→{curr_season}",
        from_fid=customer_facts.revenue_by_season_fact_ids[prev_season],
        to_fid=customer_facts.revenue_by_season_fact_ids[curr_season],
    )
    best_season, best_fid = max(
        customer_facts.revenue_by_season_fact_ids.items(), key=lambda pair: float(registry.get(pair[1]).value)
    )
    facts = {
        "revenue_prev_fact_id": customer_facts.revenue_by_season_fact_ids[prev_season],
        "revenue_curr_fact_id": customer_facts.revenue_by_season_fact_ids[curr_season],
        "revenue_delta_fact_id": revenue_delta_fid,
        "best_season_revenue_fact_id": best_fid,
    }
    for season, fid in customer_facts.revenue_by_season_fact_ids.items():
        facts[f"revenue_{season}_fact_id"] = fid
    return NarrativeFacts(
        slide_key="account_health",
        groundable=True,
        facts=facts,
        caveats=[
            f"Best season by revenue: {best_season} (see best_season_revenue_fact_id) — state it as that, not as a separate claim.",
            "No account-level volume/quantity figure is provided: products use different units of measure "
            "(L, kg, ha, ...), so summing their quantities into one 'total volume' number would be meaningless. "
            "Do not compute or invent an account-wide volume-growth figure.",
        ],
    )


def _portfolio_shifts_facts(customer_facts: CustomerFacts) -> NarrativeFacts:
    registry = customer_facts.registry
    prev_season, curr_season = _latest_two_seasons(customer_facts)
    deltas = [
        (product, _product_revenue_delta(registry, product, prev_season, curr_season)) for product in customer_facts.products
    ]
    deltas = [(p, fid) for p, fid in deltas if fid is not None]
    ranked = sorted(deltas, key=lambda pair: float(registry.get(pair[1]).value), reverse=True)

    facts: dict[str, str] = {}
    for i, (product, delta_fid) in enumerate(ranked[:3], start=1):
        facts[f"winner_{i}_name_fact_id"] = product.name_fact_id
        facts[f"winner_{i}_delta_fact_id"] = delta_fid
    for i, (product, delta_fid) in enumerate(reversed(ranked[-2:]), start=1):
        facts[f"bleeder_{i}_name_fact_id"] = product.name_fact_id
        facts[f"bleeder_{i}_delta_fact_id"] = delta_fid

    return NarrativeFacts(
        slide_key="portfolio_shifts",
        groundable=True,
        facts=facts,
        caveats=[
            "'Winners'/'bleeders' here are ranked by revenue change only — no premium-vs-commodity "
            "segment classification exists in the current data, so do not claim a product is "
            "'premium' or 'commodity' unless that is one of the given facts.",
            "'Revenue lost' for a bleeder is the delta fact itself (already negative) — report it "
            "directly, it is not an estimate.",
        ],
    )
