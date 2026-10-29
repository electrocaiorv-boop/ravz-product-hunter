"""Deterministic Supplier / sourcing-viability analysis.

This module knows NOTHING about HTTP, Apify, Mercado Livre, browser
automation, scraping, n8n, or LLMs -- it only imports
`src.supplier_models`. Given the same `SupplierInputs`,
`analyze_supplier()` always returns an identical `SupplierAnalysisResult`.

== The business question ==

    "Can I realistically source this product from this supplier under
    acceptable commercial and operational conditions?"

Distinct from Demand (market interest), Competition (competitive
difficulty), and Margin (unit-economics viability of the SALE). A
supplier's `unit_cost` is recorded here as sourcing evidence, but this
module NEVER computes a contribution margin or profitability verdict
from it -- that is `src/margin_analysis.py`'s job, not duplicated here.

== Supplier Score vs. Evidence Completeness ==

These answer different questions, exactly like Demand/Confidence
(Phase 5) and Margin Score/Cost Completeness (Phase 7):

    Supplier Score          -- "how good do the KNOWN conditions look?"
    Evidence Completeness   -- "how much do we actually know about this
                                supplier?"

`Supplier Score: 85, Evidence Completeness: 35` means the few things we
know look excellent, but we know little. `Supplier Score: 50, Evidence
Completeness: 95` means we know a lot, and it's mediocre. Missing
fields are NEVER rewarded -- excluding a field from scoring is not the
same as scoring it favorably.

== Boolean tri-state, preserved throughout ==

Every `bool | None` input keeps its three states through scoring:
`True`/`False` each contribute a real value (100/0) to their dimension;
`None` EXCLUDES that signal entirely (dimension weight renormalized
over what remains) -- never defaulted to `False`'s score of 0.

== Hard blockers are shown ALONGSIDE the score, never hidden inside it ==

A single weighted average can hide a disqualifying fact (e.g. zero
stock) inside an otherwise-decent-looking number. This module computes
`supplier_score` normally from whatever is known, and SEPARATELY
detects blockers -- both are always shown together
(`Supplier Score: 82, Operational Status: BLOCKED`), because that is
more honest than a high average quietly absorbing a disqualifying fact.

Two conditions are treated as true hard blockers (deliberately
conservative -- see docs/LEARNING.md Fase 8 for the reasoning behind
what was INCLUDED and REJECTED):

    1. stock_quantity == 0, or stock_available is False
       (known non-viable stock)
    2. stock_quantity is known AND moq_units is known AND
       0 < stock_quantity < moq_units
       (known stock cannot fill a minimum order)

`dropshipping_supported == False` is deliberately NOT a hard blocker:
not every sourcing scenario requires dropshipping (bulk purchase +
self-fulfillment remains viable), so this reduces
`fulfillment_capability_score` instead of disqualifying the supplier
outright. Invalid negative commercial data is prevented upstream by
`SupplierInputs` validation, so it never reaches this module as a
runtime blocker.

== Operational status vocabulary ==

    BLOCKED           -- a hard blocker is present (checked first,
                         regardless of score/completeness)
    INSUFFICIENT_DATA -- no blocker, but `supplier_score` is withheld
                         (evidence completeness below the minimum --
                         see below)
    VIABLE            -- no blocker, a score exists, and it meets
                         SUPPLIER_SCORE_VIABLE_THRESHOLD (50)
    CAUTION           -- no blocker, a score exists, but it's below
                         that threshold

== Evidence Completeness: WEIGHTED, not a flat count ==

Unlike Phase 7's flat `known/8`, not every field here is equally
informative -- knowing the supplier's name is far less important than
knowing MOQ, stock, dispatch timing, dropshipping capability, or
invoice status. `EVIDENCE_WEIGHTS` assigns each of 16 evidence fields a
documented share of 100%, summing to exactly 1.0; `moq_units` (0.12),
`dropshipping_supported` (0.12), `stock_quantity` (0.10), and
`operational_timing_known` (0.10, derived lead time) are the highest-
weighted, matching the Phase 8 instructions' explicit emphasis.
`product_name`/`supplier_name` are prerequisites, not evidence, and
are excluded from this count entirely (same treatment as Phase 7's
mandatory `sale_price`/`product_cost`).

`supplier_score` is withheld (`None`) unless
`evidence_completeness_score` reaches `MIN_COMPLETENESS_FOR_SCORE`
(35%) -- a different, independently-justified threshold from Phase 7's
50%, because supplier evidence is inherently sparser and harder to
obtain upfront than a seller's own cost categories.

== Supplier Score (0-100) -- PROVISIONAL business heuristic ==

Five dimensions, weighted average over whichever are available
(missing dimensions excluded, weights renormalized -- never defaulted,
never scored as a fabricated value):

    order_flexibility_score      (base weight 0.25): from moq_units
        and/or minimum_order_value, piecewise-linear, lower = more
        flexible = higher score (MOQ 1 scores highest).
    operational_speed_score       (base weight 0.20): from the derived
        lead time (see below), piecewise-linear, shorter = higher score.
    stock_viability_score         (base weight 0.20): from
        stock_quantity / stock_available / their relationship to MOQ.
    fulfillment_capability_score  (base weight 0.15): from
        dropshipping_supported (50% within this dimension, reflecting
        this project's actual dropship-focused use case),
        blind_shipping_supported (25%), tracking_available (25%).
    trust_score                   (base weight 0.20): from
        invoice_available / return_policy_available / business_verified
        / contact_available (equal weight each) plus supplier_rating,
        whose contribution is shrunk toward a neutral 50 based on
        review_count (see "Rating credibility" below) -- a 5.0 rating
        on 2 reviews must NOT equal a 4.8 rating on 10,000 reviews.

== Lead time derivation ==

    derived_lead_time_days = lead_time_days, if explicitly given
                              else dispatch_time_days + delivery_time_days,
                              if BOTH are known
                              else None (only one of the two known is
                              NOT enough to claim a total)

== Rating credibility (conservative, deterministic) ==

    normalized_rating = (supplier_rating / 5) * 100
    credibility       = piecewise-linear over review_count (0 reviews,
                         or unknown review_count, -> 0.1; 200+ -> 1.0)
    effective_rating  = 50 + credibility * (normalized_rating - 50)

A high rating with few/unknown reviews shrinks toward the neutral
midpoint (50) instead of being trusted at face value; a high rating
with many reviews approaches its true value. This is the "simple
deterministic confidence adjustment" the Phase 8 instructions asked
for -- not fabricated statistical sophistication (no confidence
intervals, no Bayesian priors), just a documented, testable shrinkage.

All weights/anchors/thresholds are module-level constants, meant to be
recalibrated once real outcome data exists -- not treated as final.
This Supplier Score is NOT wired into the Phase 1 Opportunity Scoring
Engine yet.
"""

from dataclasses import dataclass, field

from src.supplier_models import SupplierInputs

WEIGHT_ORDER_FLEXIBILITY = 0.25
WEIGHT_OPERATIONAL_SPEED = 0.20
WEIGHT_STOCK_VIABILITY = 0.20
WEIGHT_FULFILLMENT_CAPABILITY = 0.15
WEIGHT_TRUST = 0.20

MIN_COMPLETENESS_FOR_SCORE = 0.35
SUPPLIER_SCORE_VIABLE_THRESHOLD = 50.0

# Piecewise-linear anchors: (x, score). PROVISIONAL, documented,
# adjustable -- not universal truths. See module docstring.
MOQ_FLEXIBILITY_ANCHORS = ((1, 100.0), (10, 80.0), (50, 50.0), (100, 30.0), (500, 10.0), (1000, 0.0))
MIN_ORDER_VALUE_ANCHORS = ((0, 100.0), (200, 80.0), (1000, 50.0), (5000, 20.0), (20000, 0.0))
LEAD_TIME_ANCHORS = ((1, 100.0), (7, 85.0), (15, 65.0), (30, 40.0), (60, 15.0), (90, 0.0))
STOCK_MOQ_RATIO_ANCHORS = ((1, 60.0), (2, 75.0), (5, 90.0), (10, 100.0))
STOCK_ABSOLUTE_ANCHORS = ((1, 30.0), (10, 50.0), (100, 75.0), (500, 90.0), (1000, 100.0))
STOCK_AVAILABLE_FLAT_SCORE = 55.0  # known available, quantity unknown -- weaker than a known healthy quantity
RATING_CREDIBILITY_ANCHORS = ((0, 0.1), (1, 0.15), (5, 0.35), (20, 0.6), (50, 0.8), (200, 1.0))

# Weighted evidence completeness -- sums to exactly 1.0. See module
# docstring for why this is weighted, not a flat count.
EVIDENCE_WEIGHTS = {
    "unit_cost": 0.05,
    "moq_units": 0.12,
    "minimum_order_value": 0.05,
    "shipping_cost": 0.05,
    "payment_terms_days": 0.03,
    "stock_quantity": 0.10,
    "stock_available": 0.05,
    "operational_timing_known": 0.10,
    "tracking_available": 0.05,
    "dropshipping_supported": 0.12,
    "blind_shipping_supported": 0.05,
    "invoice_available": 0.08,
    "return_policy_available": 0.04,
    "business_verified": 0.04,
    "contact_available": 0.02,
    "supplier_rating": 0.05,
}


def _interpolate(x, anchors) -> float:
    """Piecewise-linear interpolation over (x, y) anchors, clamped at the ends."""
    x = float(x)
    if x <= anchors[0][0]:
        return anchors[0][1]
    if x >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= x <= x1:
            ratio = (x - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    return anchors[-1][1]  # unreachable; anchors are exhaustive by construction


@dataclass
class SupplierAnalysisResult:
    """Deterministic output of analyze_supplier(). supplier_score is PROVISIONAL."""

    product_name: str
    supplier_name: str
    supplier_score: float | None
    evidence_completeness_score: float
    operational_status: str
    order_flexibility_score: float | None
    operational_speed_score: float | None
    stock_viability_score: float | None
    fulfillment_capability_score: float | None
    trust_score: float | None
    lead_time_days: int | None
    observed: dict
    derived: dict
    unavailable: list[str]
    blockers: list[str]
    warnings: list[str]
    notes: list[str] = field(default_factory=list)


def _derived_lead_time_days(inputs: SupplierInputs) -> int | None:
    if inputs.lead_time_days is not None:
        return inputs.lead_time_days
    if inputs.dispatch_time_days is not None and inputs.delivery_time_days is not None:
        return inputs.dispatch_time_days + inputs.delivery_time_days
    return None


def _order_flexibility_score(inputs: SupplierInputs) -> float | None:
    moq_score = _interpolate(inputs.moq_units, MOQ_FLEXIBILITY_ANCHORS) if inputs.moq_units is not None else None
    value_score = (
        _interpolate(inputs.minimum_order_value, MIN_ORDER_VALUE_ANCHORS)
        if inputs.minimum_order_value is not None
        else None
    )
    if moq_score is None and value_score is None:
        return None
    if moq_score is not None and value_score is not None:
        return moq_score * 0.6 + value_score * 0.4
    return moq_score if moq_score is not None else value_score


def _operational_speed_score(lead_time_days: int | None) -> float | None:
    if lead_time_days is None:
        return None
    return _interpolate(lead_time_days, LEAD_TIME_ANCHORS)


def _stock_viability_score(inputs: SupplierInputs) -> float | None:
    if inputs.stock_quantity is not None:
        if inputs.stock_quantity == 0:
            return 0.0
        if inputs.moq_units is not None:
            if inputs.stock_quantity < inputs.moq_units:
                return 10.0
            ratio = inputs.stock_quantity / inputs.moq_units
            return _interpolate(ratio, STOCK_MOQ_RATIO_ANCHORS)
        return _interpolate(inputs.stock_quantity, STOCK_ABSOLUTE_ANCHORS)
    if inputs.stock_available is False:
        return 0.0
    if inputs.stock_available is True:
        return STOCK_AVAILABLE_FLAT_SCORE
    return None


def _fulfillment_capability_score(inputs: SupplierInputs) -> float | None:
    parts = []
    if inputs.dropshipping_supported is not None:
        parts.append((100.0 if inputs.dropshipping_supported else 0.0, 0.5))
    if inputs.blind_shipping_supported is not None:
        parts.append((100.0 if inputs.blind_shipping_supported else 0.0, 0.25))
    if inputs.tracking_available is not None:
        parts.append((100.0 if inputs.tracking_available else 0.0, 0.25))
    if not parts:
        return None
    total_weight = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / total_weight


def _rating_credibility(review_count: int | None) -> float:
    effective_count = review_count if review_count is not None else 0
    return _interpolate(effective_count, RATING_CREDIBILITY_ANCHORS)


def _trust_score(inputs: SupplierInputs) -> float | None:
    parts = []
    for value in (
        inputs.invoice_available,
        inputs.return_policy_available,
        inputs.business_verified,
        inputs.contact_available,
    ):
        if value is not None:
            parts.append((100.0 if value else 0.0, 1.0))
    if inputs.supplier_rating is not None:
        normalized = float(inputs.supplier_rating) / 5 * 100
        credibility = _rating_credibility(inputs.review_count)
        effective = 50 + credibility * (normalized - 50)
        parts.append((effective, 1.0))
    if not parts:
        return None
    total_weight = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / total_weight


def _detect_blockers(inputs: SupplierInputs) -> list[str]:
    blockers = []
    if inputs.stock_quantity == 0:
        blockers.append("no stock available (stock_quantity = 0)")
    if inputs.stock_available is False and inputs.stock_quantity != 0:
        blockers.append("supplier reports stock not currently available (stock_available = False)")
    if (
        inputs.moq_units is not None
        and inputs.stock_quantity is not None
        and 0 < inputs.stock_quantity < inputs.moq_units
    ):
        blockers.append(
            f"stock_quantity ({inputs.stock_quantity}) is below moq_units "
            f"({inputs.moq_units}) -- known stock cannot fill a minimum order"
        )
    return blockers


def _evidence_completeness_score(inputs: SupplierInputs, derived_lead_time: int | None) -> float:
    known_weight = 0.0
    for field_name, weight in EVIDENCE_WEIGHTS.items():
        if field_name == "operational_timing_known":
            known = derived_lead_time is not None
        else:
            known = getattr(inputs, field_name) is not None
        if known:
            known_weight += weight
    return round(known_weight * 100, 2)


def analyze_supplier(inputs: SupplierInputs) -> SupplierAnalysisResult:
    """Compute a deterministic, provisional Supplier Score and Evidence Completeness."""
    notes: list[str] = []
    warnings: list[str] = []

    lead_time_days = _derived_lead_time_days(inputs)
    if lead_time_days is not None and inputs.lead_time_days is None:
        notes.append("lead_time_days derived as dispatch_time_days + delivery_time_days")

    order_flexibility = _order_flexibility_score(inputs)
    operational_speed = _operational_speed_score(lead_time_days)
    stock_viability = _stock_viability_score(inputs)
    fulfillment_capability = _fulfillment_capability_score(inputs)
    trust = _trust_score(inputs)

    components = (
        (order_flexibility, WEIGHT_ORDER_FLEXIBILITY),
        (operational_speed, WEIGHT_OPERATIONAL_SPEED),
        (stock_viability, WEIGHT_STOCK_VIABILITY),
        (fulfillment_capability, WEIGHT_FULFILLMENT_CAPABILITY),
        (trust, WEIGHT_TRUST),
    )
    available = [(c, w) for c, w in components if c is not None]

    unavailable = []
    if order_flexibility is None:
        unavailable.append("order flexibility (MOQ / minimum order value)")
    if operational_speed is None:
        unavailable.append("operational speed (lead time)")
    if stock_viability is None:
        unavailable.append("stock viability")
    if fulfillment_capability is None:
        unavailable.append("fulfillment capability (dropshipping / blind shipping / tracking)")
    if trust is None:
        unavailable.append("trust/compliance signals")
    unavailable.append("price stability / catalog stability (no historical observations)")
    unavailable.append("historical fulfillment rate (no historical data)")

    evidence_completeness_score = _evidence_completeness_score(inputs, lead_time_days)

    blockers = _detect_blockers(inputs)

    if evidence_completeness_score / 100.0 >= MIN_COMPLETENESS_FOR_SCORE and available:
        total_weight = sum(w for _, w in available)
        supplier_score = round(sum(c * w for c, w in available) / total_weight, 2)
    else:
        supplier_score = None
        notes.append(
            f"Supplier Score withheld: evidence completeness is "
            f"{evidence_completeness_score:.2f}% (below the "
            f"{int(MIN_COMPLETENESS_FOR_SCORE * 100)}% minimum) -- a single 0-100 "
            "score from this little evidence would be misleading"
        )

    if blockers:
        operational_status = "BLOCKED"
    elif supplier_score is None:
        operational_status = "INSUFFICIENT_DATA"
    elif supplier_score >= SUPPLIER_SCORE_VIABLE_THRESHOLD:
        operational_status = "VIABLE"
    else:
        operational_status = "CAUTION"

    if inputs.supplier_rating is not None and (inputs.review_count or 0) < 5:
        warnings.append(
            "supplier_rating is based on very few (or unknown) reviews -- "
            "treat it with low confidence, not as a reliable signal"
        )
    if inputs.moq_units is not None and inputs.moq_units >= 100:
        warnings.append(
            f"MOQ ({inputs.moq_units} units) is high -- may represent a significant "
            "inventory commitment for a small seller"
        )
    if inputs.stock_available is True and inputs.stock_quantity is None:
        warnings.append("stock is reported available, but the exact quantity is unknown")
    if inputs.dropshipping_supported is False:
        warnings.append(
            "dropshipping is not supported by this supplier -- bulk purchase and "
            "self-fulfillment would be required instead"
        )

    observed = {
        "unit_cost": inputs.unit_cost,
        "moq_units": inputs.moq_units,
        "minimum_order_value": inputs.minimum_order_value,
        "shipping_cost": inputs.shipping_cost,
        "stock_quantity": inputs.stock_quantity,
        "stock_available": inputs.stock_available,
        "dispatch_time_days": inputs.dispatch_time_days,
        "delivery_time_days": inputs.delivery_time_days,
        "dropshipping_supported": inputs.dropshipping_supported,
        "blind_shipping_supported": inputs.blind_shipping_supported,
        "invoice_available": inputs.invoice_available,
        "return_policy_available": inputs.return_policy_available,
        "business_verified": inputs.business_verified,
        "contact_available": inputs.contact_available,
        "supplier_rating": inputs.supplier_rating,
        "review_count": inputs.review_count,
        "years_active": inputs.years_active,
    }
    derived = {
        "lead_time_days": lead_time_days,
        "order_flexibility_score": order_flexibility,
        "operational_speed_score": operational_speed,
        "stock_viability_score": stock_viability,
        "fulfillment_capability_score": fulfillment_capability,
        "trust_score": trust,
    }

    return SupplierAnalysisResult(
        product_name=inputs.product_name,
        supplier_name=inputs.supplier_name,
        supplier_score=supplier_score,
        evidence_completeness_score=evidence_completeness_score,
        operational_status=operational_status,
        order_flexibility_score=order_flexibility,
        operational_speed_score=operational_speed,
        stock_viability_score=stock_viability,
        fulfillment_capability_score=fulfillment_capability,
        trust_score=trust,
        lead_time_days=lead_time_days,
        observed=observed,
        derived=derived,
        unavailable=unavailable,
        blockers=blockers,
        warnings=warnings,
        notes=notes,
    )
