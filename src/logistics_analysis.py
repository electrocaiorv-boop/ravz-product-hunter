"""Deterministic Logistics analysis.

This module knows NOTHING about HTTP, Apify, Mercado Livre, carrier
APIs, browser automation, scraping, n8n, or LLMs -- it only imports
`src.logistics_models`. Given the same `LogisticsInputs`,
`analyze_logistics()` always returns an identical `LogisticsAnalysisResult`.

== The business question ==

    "How operationally difficult is this product to move from source
    to customer?"

Distinct from Demand, Competition, Margin ("does each known sale
appear financially viable?"), and Supplier ("can we source the product
reliably?"). Logistics asks: can we store, handle, ship, and deliver
it efficiently and safely? `known_shipping_cost` is recorded as
observed evidence only -- this module has no `sale_price` field and
therefore cannot compute profitability even by accident; that stays
exclusively in `src/margin_analysis.py`.

== Customer delivery time != supplier lead time ==

`estimated_delivery_days` is the LAST-MILE leg (seller/warehouse to
customer). Phase 8's `lead_time_days` is the SOURCING leg (supplier to
seller). These are different legs of the same overall journey and must
never be read as interchangeable -- this module never imports anything
from `src.supplier_analysis` or `src.supplier_models`.

== Score direction: 0 = difficult, 100 = easy/favorable ==

This is the OPPOSITE convention from an internal "burden" framing.
Every dimension function below is written to directly return an EASE
value (anchors go from "hard" at low x to "easy" at high x, or are
built from a burden computed first and then inverted via
`100 - burden` -- always documented per dimension). Higher
Logistics Score = better opportunity, matching Phase 1's existing
convention of treating logistics as a positive dimension.

== Observed rate vs. inferred risk (kept architecturally separate) ==

`observed_damage_rate` / `observed_return_rate` are REAL historical
observations. `fragile`/`hazardous`/etc. are PROPERTY flags that
inform a risk INDICATOR (`handling_ease_score`). These are
deliberately NEVER blended into the same number: a fragile product
gets a lower `handling_ease_score` (an indicator, "this looks
riskier"), which is NOT the same claim as "this has a 15% damage
rate" (a fabricated statistic). The two feed different, clearly
labeled outputs: `handling_ease_score` (one of the 5 scored
dimensions) vs. `observed` evidence + hard-blocker detection (below).
Neither is computed from the other.

== Hard blockers: NONE are currently reachable, by design ==

A hard blocker must mean "we have evidence the operation is currently
IMPOSSIBLE," not "we have evidence the operation went badly." Phase 8's
`stock_quantity == 0` qualifies because it's a direct contradiction (no
stock, no sale). Nothing in `LogisticsInputs` reaches that bar:

A 50%+ `observed_damage_rate`/`observed_return_rate` was INITIALLY
treated as a hard blocker in this phase, but that was a semantic bug,
caught and corrected during hardening review: a 55% observed damage
rate means "historical logistics performance here is extremely poor,"
not "shipping is impossible." If 45% of shipments arrived fine, fulfillment
plainly CAN be performed -- it's just performed badly. Conflating
"bad outcome" with "impossible operation" would silently misrepresent
what the evidence actually proves. See `docs/LEARNING.md` ("Bad outcome
!= impossible operation") for the full worked-out reasoning.

The Phase 9 source evaluation also found no other genuine, provable
contradiction reachable from this field set without either (a)
inventing a capability field we don't have (e.g. a fictional
"cold_chain_supported" flag, needed to turn `temperature_sensitive=True`
into a real blocker), or (b) making a legal/regulatory judgment (e.g.
declaring a hazardous+liquid combination "cannot be shipped", which is
a compliance conclusion this module is not qualified to assert
deterministically). Both are explicitly out of scope.

`_detect_blockers()` therefore always returns an empty list today, and
`BLOCKED` is consequently UNREACHABLE from any current input
combination. Both the function and the `BLOCKED` status value are kept
-- not dead code to be deleted, but a reserved extension point: if a
future field genuinely proves impossibility (e.g. a verified "carrier
refused this shipment" flag, or a real stock-out equivalent for
logistics), it belongs in `_detect_blockers()`, checked first, exactly
like every other phase's blocker-precedence rule. Do not repurpose it
for severity -- that's what `CAUTION` and the warnings list are for.

A severe observed damage/return rate (>= 50%, provisional) instead
produces a WARNING (see `_detect_severe_observed_warnings()`) and
forces `operational_status` to at least `CAUTION`, without touching
`logistics_score`'s own calculation or forcing it to `None` -- the
score still reflects whatever OTHER dimensions are known,
independently of this warning. Every other risky combination (e.g.
`temperature_sensitive=True` with a long `estimated_delivery_days`)
also produces a WARNING, never a blocker -- same "prefer CAUTION over
an unproven BLOCKED" principle, applied consistently.

== Logistics Score (0-100) -- PROVISIONAL business heuristic ==

Five dimensions, weighted average over whichever are available
(missing dimensions excluded, weights renormalized -- never defaulted,
never scored as a fabricated value):

    physical_ease_score        (base weight 0.30): from weight/size.
        Prefers `reference_billable_weight` (see below) over raw
        `weight_kg` when both volume and weight are known, since it
        better reflects real shipping burden; blended 60/40 with a
        volume-based ease score when both are available.
    handling_ease_score          (base weight 0.25): from the 6 risk
        flags (fragile/liquid/hazardous/perishable/temperature_sensitive/
        requires_special_handling) plus `stackable`. Each KNOWN flag
        contributes an ease value (True-risk -> low ease, False-risk
        -> high ease, confirming absence of risk is itself good
        evidence), blended over whichever are known.
    delivery_convenience_score   (base weight 0.20): from
        `estimated_delivery_days` (customer-facing only).
    fulfillment_support_score    (base weight 0.15): from
        `supplier_fulfilled`/`seller_fulfilled`/`warehouse_required`.
    shipping_support_score       (base weight 0.10): from
        `tracking_available`/`insurance_available`.

== Package volume, dimensional weight, "reference" billable weight ==

    package_volume_cm3 = length_cm * width_cm * height_cm
                          (ONLY if all three are known -- a partial
                          set of dimensions never produces a partial
                          or guessed volume)
    volume_liters       = package_volume_cm3 / 1000
    dimensional_weight_kg = package_volume_cm3 / dimensional_weight_divisor
                          (ONLY if both the volume AND an explicitly
                          supplied divisor are known -- never a
                          hardcoded divisor)
    reference_billable_weight = max(weight_kg, dimensional_weight_kg)
                          (ONLY if both are known; explicitly labeled
                          "reference" throughout -- this is a generic,
                          illustrative comparison, NEVER presented as
                          an actual carrier's billing weight, which
                          depends on carrier-specific contracts this
                          project does not have.)

== Evidence Completeness: WEIGHTED, not a flat count ==

Same reasoning as Phase 8: weight/dimensions/fragility matter far more
than, say, insurance availability. 20 evidence items (the three raw
dimensions `length_cm`/`width_cm`/`height_cm` count as ONE combined
"dimensions_known" bucket, exactly like Phase 8 treated lead-time
components, to avoid rewarding partial dimension knowledge
disproportionately) with documented weights summing to exactly 1.0.

`logistics_score` is withheld (`None`) unless `evidence_completeness_score`
reaches `MIN_COMPLETENESS_FOR_SCORE` (40%) -- an independently chosen,
documented threshold (different from Phase 7's 50% and Phase 8's 35%):
physical facts (weight, dimensions) are typically easier for a seller
to obtain upfront than full supplier commercial terms, so a
moderately higher bar than Phase 8's is reasonable before trusting a
single verdict, without being as strict as Phase 7's cost-category bar.

== Operational status ==

    BLOCKED           -- a hard blocker is present (see above; checked
                         first). UNREACHABLE today -- reserved for a
                         future field that can prove impossibility.
    CAUTION           -- a severe observed damage/return rate warning
                         is present (checked second, regardless of
                         `logistics_score`), OR no blocker/severe
                         warning and score < 50
    INSUFFICIENT_DATA -- no blocker, no severe warning, but
                         `logistics_score` is withheld (evidence too
                         thin to trust a single verdict)
    EASY              -- no blocker, no severe warning, score >= 75
    MANAGEABLE        -- no blocker, no severe warning, 50 <= score < 75

A severe warning is checked BEFORE the completeness gate deliberately:
an observed damage/return rate is concrete, specific evidence in its
own right, even when other fields (weight, handling flags, etc.) are
unknown -- calling that situation merely "insufficient data" would
bury a real, serious signal we do have under a vague one about data we
don't have.

All weights/anchors/thresholds are module-level constants, meant to be
recalibrated once real outcome data exists -- not treated as final.
This Logistics Score is NOT wired into the Phase 1 Opportunity Scoring
Engine yet.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from src.logistics_models import LogisticsInputs

WEIGHT_PHYSICAL_EASE = 0.30
WEIGHT_HANDLING_EASE = 0.25
WEIGHT_DELIVERY_CONVENIENCE = 0.20
WEIGHT_FULFILLMENT_SUPPORT = 0.15
WEIGHT_SHIPPING_SUPPORT = 0.10

MIN_COMPLETENESS_FOR_SCORE = 0.40
EASY_THRESHOLD = 75.0
MANAGEABLE_THRESHOLD = 50.0

DAMAGE_RATE_SEVERE_WARNING_THRESHOLD = Decimal("0.5")
RETURN_RATE_SEVERE_WARNING_THRESHOLD = Decimal("0.5")

# Piecewise-linear anchors: (x, ease_score). PROVISIONAL, documented,
# adjustable -- not universal carrier/marketplace truths.
WEIGHT_EASE_ANCHORS = ((0.5, 100.0), (1, 90.0), (5, 65.0), (10, 40.0), (20, 15.0), (30, 0.0))
VOLUME_EASE_ANCHORS = ((1, 100.0), (5, 85.0), (20, 60.0), (50, 30.0), (100, 0.0))
DELIVERY_EASE_ANCHORS = ((2, 100.0), (5, 85.0), (10, 60.0), (20, 30.0), (30, 0.0))

# Handling sub-signal ease values: (ease_if_true, ease_if_false, weight).
# "True" = risk property present; "False" = verified absent (good
# evidence); weight reflects provisional severity.
HANDLING_SUB_SIGNALS = {
    "fragile": (40.0, 100.0, 1.0),
    "liquid": (45.0, 100.0, 1.0),
    "hazardous": (20.0, 100.0, 1.2),
    "perishable": (45.0, 100.0, 1.0),
    "temperature_sensitive": (45.0, 100.0, 1.0),
    "requires_special_handling": (30.0, 100.0, 1.2),
    "stackable": (100.0, 70.0, 0.6),
}

FULFILLMENT_SUB_SIGNALS = {
    "supplier_fulfilled": (100.0, 60.0, 1.0),
    "seller_fulfilled": (50.0, 80.0, 0.8),
    "warehouse_required": (40.0, 90.0, 1.0),
}

# Weighted evidence completeness -- sums to exactly 1.0.
EVIDENCE_WEIGHTS = {
    "weight_kg": 0.12,
    "dimensions_known": 0.12,
    "fragile": 0.10,
    "liquid": 0.04,
    "hazardous": 0.06,
    "perishable": 0.05,
    "temperature_sensitive": 0.05,
    "stackable": 0.03,
    "requires_special_handling": 0.05,
    "extra_packaging_required": 0.02,
    "packaging_cost": 0.02,
    "supplier_fulfilled": 0.05,
    "seller_fulfilled": 0.03,
    "warehouse_required": 0.04,
    "known_shipping_cost": 0.04,
    "estimated_delivery_days": 0.06,
    "tracking_available": 0.02,
    "insurance_available": 0.02,
    "observed_damage_rate": 0.04,
    "observed_return_rate": 0.04,
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
class LogisticsAnalysisResult:
    """Deterministic output of analyze_logistics(). logistics_score is PROVISIONAL."""

    product_name: str
    logistics_score: float | None
    evidence_completeness_score: float
    operational_status: str
    physical_ease_score: float | None
    handling_ease_score: float | None
    delivery_convenience_score: float | None
    fulfillment_support_score: float | None
    shipping_support_score: float | None
    package_volume_cm3: Decimal | None
    volume_liters: Decimal | None
    dimensional_weight_kg: Decimal | None
    reference_billable_weight_kg: Decimal | None
    observed: dict
    derived: dict
    unavailable: list[str]
    blockers: list[str]
    warnings: list[str]
    notes: list[str] = field(default_factory=list)


def _package_volume_cm3(inputs: LogisticsInputs) -> Decimal | None:
    if inputs.length_cm is None or inputs.width_cm is None or inputs.height_cm is None:
        return None
    return inputs.length_cm * inputs.width_cm * inputs.height_cm


def _volume_liters(volume_cm3: Decimal | None) -> Decimal | None:
    if volume_cm3 is None:
        return None
    return volume_cm3 / Decimal("1000")


def _dimensional_weight_kg(volume_cm3: Decimal | None, divisor: Decimal | None) -> Decimal | None:
    if volume_cm3 is None or divisor is None:
        return None
    return volume_cm3 / divisor


def _reference_billable_weight_kg(
    weight_kg: Decimal | None, dimensional_weight_kg: Decimal | None
) -> Decimal | None:
    if weight_kg is None or dimensional_weight_kg is None:
        return None
    return max(weight_kg, dimensional_weight_kg)


def _physical_ease_score(
    inputs: LogisticsInputs, reference_billable_weight_kg: Decimal | None, volume_liters: Decimal | None
) -> float | None:
    weight_basis = reference_billable_weight_kg if reference_billable_weight_kg is not None else inputs.weight_kg
    weight_score = _interpolate(weight_basis, WEIGHT_EASE_ANCHORS) if weight_basis is not None else None
    volume_score = _interpolate(volume_liters, VOLUME_EASE_ANCHORS) if volume_liters is not None else None

    if weight_score is None and volume_score is None:
        return None
    if weight_score is not None and volume_score is not None:
        return weight_score * 0.6 + volume_score * 0.4
    return weight_score if weight_score is not None else volume_score


def _blend_sub_signals(inputs: LogisticsInputs, signal_table: dict) -> float | None:
    parts = []
    for field_name, (ease_if_true, ease_if_false, weight) in signal_table.items():
        value = getattr(inputs, field_name)
        if value is not None:
            parts.append((ease_if_true if value else ease_if_false, weight))
    if not parts:
        return None
    total_weight = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / total_weight


def _handling_ease_score(inputs: LogisticsInputs) -> float | None:
    return _blend_sub_signals(inputs, HANDLING_SUB_SIGNALS)


def _fulfillment_support_score(inputs: LogisticsInputs) -> float | None:
    return _blend_sub_signals(inputs, FULFILLMENT_SUB_SIGNALS)


def _delivery_convenience_score(inputs: LogisticsInputs) -> float | None:
    if inputs.estimated_delivery_days is None:
        return None
    return _interpolate(inputs.estimated_delivery_days, DELIVERY_EASE_ANCHORS)


def _shipping_support_score(inputs: LogisticsInputs) -> float | None:
    parts = []
    if inputs.tracking_available is not None:
        parts.append((100.0 if inputs.tracking_available else 0.0, 1.0))
    if inputs.insurance_available is not None:
        parts.append((100.0 if inputs.insurance_available else 0.0, 1.0))
    if not parts:
        return None
    total_weight = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / total_weight


def _detect_blockers(inputs: LogisticsInputs) -> list[str]:
    """Genuine proof-of-impossibility contradictions only -- see module
    docstring ("Hard blockers: NONE are currently reachable, by design").

    No field in the current `LogisticsInputs` schema can prove that
    fulfillment is currently IMPOSSIBLE (as opposed to merely bad), so
    this always returns an empty list today. Kept as a reserved
    extension point for a future field that genuinely can (e.g. a
    verified "carrier refused this shipment" flag) -- never repurpose
    it for severity; that's what `_detect_severe_observed_warnings()`
    and `CAUTION` are for.
    """
    return []


def _detect_severe_observed_warnings(inputs: LogisticsInputs) -> list[str]:
    """Severe (but NOT impossibility-proving) observed damage/return rate.

    `observed_damage_rate`/`observed_return_rate` are real historical
    evidence. A high rate (>= 50%, provisional) is strong NEGATIVE
    evidence of poor operational performance -- but every shipment that
    did NOT get damaged/returned is direct proof the operation is not
    physically impossible. This is why a severe rate produces a warning
    (and forces `operational_status` to at least CAUTION) rather than a
    hard blocker. An explicit `0` is equally meaningful positive
    evidence and intentionally produces no warning here; `None`
    (unknown) is excluded entirely, never treated as either.
    """
    warnings = []
    if (
        inputs.observed_damage_rate is not None
        and inputs.observed_damage_rate >= DAMAGE_RATE_SEVERE_WARNING_THRESHOLD
    ):
        warnings.append(
            f"observed damage rate is {inputs.observed_damage_rate} -- at or above "
            f"{DAMAGE_RATE_SEVERE_WARNING_THRESHOLD}, this is severe negative operational "
            "evidence (extremely poor historical performance), but it does NOT by itself "
            "prove fulfillment is impossible -- the shipments that were NOT damaged are "
            "proof otherwise; this forces CAUTION, not BLOCKED"
        )
    if (
        inputs.observed_return_rate is not None
        and inputs.observed_return_rate >= RETURN_RATE_SEVERE_WARNING_THRESHOLD
    ):
        warnings.append(
            f"observed return rate is {inputs.observed_return_rate} -- at or above "
            f"{RETURN_RATE_SEVERE_WARNING_THRESHOLD}, this is severe negative operational "
            "evidence (extremely poor historical performance), but it does NOT by itself "
            "prove fulfillment is impossible -- the sales that were NOT returned are proof "
            "otherwise; this forces CAUTION, not BLOCKED"
        )
    return warnings


def _evidence_completeness_score(inputs: LogisticsInputs, dimensions_known: bool) -> float:
    known_weight = 0.0
    for field_name, weight in EVIDENCE_WEIGHTS.items():
        if field_name == "dimensions_known":
            known = dimensions_known
        else:
            known = getattr(inputs, field_name) is not None
        if known:
            known_weight += weight
    return round(known_weight * 100, 2)


def analyze_logistics(inputs: LogisticsInputs) -> LogisticsAnalysisResult:
    """Compute a deterministic, provisional Logistics Score and Evidence Completeness."""
    notes: list[str] = []
    warnings: list[str] = []

    package_volume_cm3 = _package_volume_cm3(inputs)
    volume_liters = _volume_liters(package_volume_cm3)
    dimensional_weight_kg = _dimensional_weight_kg(package_volume_cm3, inputs.dimensional_weight_divisor)
    reference_billable_weight_kg = _reference_billable_weight_kg(inputs.weight_kg, dimensional_weight_kg)

    if package_volume_cm3 is None and (
        inputs.length_cm is not None or inputs.width_cm is not None or inputs.height_cm is not None
    ):
        notes.append(
            "package volume unavailable: all three of length_cm/width_cm/height_cm "
            "must be known to compute volume -- a partial set is not enough"
        )

    physical_ease = _physical_ease_score(inputs, reference_billable_weight_kg, volume_liters)
    handling_ease = _handling_ease_score(inputs)
    delivery_convenience = _delivery_convenience_score(inputs)
    fulfillment_support = _fulfillment_support_score(inputs)
    shipping_support = _shipping_support_score(inputs)

    components = (
        (physical_ease, WEIGHT_PHYSICAL_EASE),
        (handling_ease, WEIGHT_HANDLING_EASE),
        (delivery_convenience, WEIGHT_DELIVERY_CONVENIENCE),
        (fulfillment_support, WEIGHT_FULFILLMENT_SUPPORT),
        (shipping_support, WEIGHT_SHIPPING_SUPPORT),
    )
    available = [(c, w) for c, w in components if c is not None]

    unavailable = []
    if physical_ease is None:
        unavailable.append("physical ease (weight / dimensions)")
    if handling_ease is None:
        unavailable.append("handling ease (fragile / liquid / hazardous / perishable / temperature / special handling)")
    if delivery_convenience is None:
        unavailable.append("delivery convenience (estimated delivery days)")
    if fulfillment_support is None:
        unavailable.append("fulfillment support (supplier/seller fulfilled, warehouse)")
    if shipping_support is None:
        unavailable.append("shipping support (tracking / insurance)")
    unavailable.append("damage probability (only an observed rate, if supplied, is ever shown -- never estimated)")
    unavailable.append("exact carrier billing weight (reference_billable_weight is a generic comparison, not a real carrier charge)")
    unavailable.append("exact marketplace oversize/restriction classification (no marketplace logistics rules are modeled)")

    dimensions_known = package_volume_cm3 is not None
    evidence_completeness_score = _evidence_completeness_score(inputs, dimensions_known)

    blockers = _detect_blockers(inputs)
    severe_observed_warnings = _detect_severe_observed_warnings(inputs)
    warnings.extend(severe_observed_warnings)

    if evidence_completeness_score / 100.0 >= MIN_COMPLETENESS_FOR_SCORE and available:
        total_weight = sum(w for _, w in available)
        logistics_score = round(sum(c * w for c, w in available) / total_weight, 2)
    else:
        logistics_score = None
        notes.append(
            f"Logistics Score withheld: evidence completeness is "
            f"{evidence_completeness_score:.2f}% (below the "
            f"{int(MIN_COMPLETENESS_FOR_SCORE * 100)}% minimum) -- a single 0-100 "
            "score from this little evidence would be misleading"
        )

    if blockers:
        operational_status = "BLOCKED"
    elif severe_observed_warnings:
        operational_status = "CAUTION"
    elif logistics_score is None:
        operational_status = "INSUFFICIENT_DATA"
    elif logistics_score >= EASY_THRESHOLD:
        operational_status = "EASY"
    elif logistics_score >= MANAGEABLE_THRESHOLD:
        operational_status = "MANAGEABLE"
    else:
        operational_status = "CAUTION"

    if inputs.temperature_sensitive and inputs.estimated_delivery_days is not None and inputs.estimated_delivery_days >= 10:
        warnings.append(
            "product is temperature-sensitive with a long estimated delivery time -- "
            "this is a risk combination, not a proven blocker (no cold-chain capability field exists)"
        )
    if inputs.hazardous and inputs.requires_special_handling is False:
        warnings.append(
            "product is hazardous but requires_special_handling is explicitly False -- "
            "double-check this is intentional, not an oversight"
        )
    if (
        reference_billable_weight_kg is not None
        and dimensional_weight_kg is not None
        and inputs.weight_kg is not None
        and dimensional_weight_kg > inputs.weight_kg
    ):
        warnings.append(
            "dimensional weight exceeds actual weight -- some carriers may bill based on "
            "the larger figure, but this is NOT a universal rule and no real carrier is consulted here"
        )

    observed = {
        "weight_kg": inputs.weight_kg,
        "length_cm": inputs.length_cm,
        "width_cm": inputs.width_cm,
        "height_cm": inputs.height_cm,
        "fragile": inputs.fragile,
        "liquid": inputs.liquid,
        "hazardous": inputs.hazardous,
        "perishable": inputs.perishable,
        "temperature_sensitive": inputs.temperature_sensitive,
        "stackable": inputs.stackable,
        "requires_special_handling": inputs.requires_special_handling,
        "extra_packaging_required": inputs.extra_packaging_required,
        "packaging_cost": inputs.packaging_cost,
        "supplier_fulfilled": inputs.supplier_fulfilled,
        "seller_fulfilled": inputs.seller_fulfilled,
        "warehouse_required": inputs.warehouse_required,
        "known_shipping_cost": inputs.known_shipping_cost,
        "estimated_delivery_days": inputs.estimated_delivery_days,
        "tracking_available": inputs.tracking_available,
        "insurance_available": inputs.insurance_available,
        "observed_damage_rate": inputs.observed_damage_rate,
        "observed_return_rate": inputs.observed_return_rate,
    }
    derived = {
        "package_volume_cm3": package_volume_cm3,
        "volume_liters": volume_liters,
        "dimensional_weight_kg": dimensional_weight_kg,
        "reference_billable_weight_kg": reference_billable_weight_kg,
        "physical_ease_score": physical_ease,
        "handling_ease_score": handling_ease,
        "delivery_convenience_score": delivery_convenience,
        "fulfillment_support_score": fulfillment_support,
        "shipping_support_score": shipping_support,
    }

    return LogisticsAnalysisResult(
        product_name=inputs.product_name,
        logistics_score=logistics_score,
        evidence_completeness_score=evidence_completeness_score,
        operational_status=operational_status,
        physical_ease_score=physical_ease,
        handling_ease_score=handling_ease,
        delivery_convenience_score=delivery_convenience,
        fulfillment_support_score=fulfillment_support,
        shipping_support_score=shipping_support,
        package_volume_cm3=package_volume_cm3,
        volume_liters=volume_liters,
        dimensional_weight_kg=dimensional_weight_kg,
        reference_billable_weight_kg=reference_billable_weight_kg,
        observed=observed,
        derived=derived,
        unavailable=unavailable,
        blockers=blockers,
        warnings=warnings,
        notes=notes,
    )
