"""Tests for the deterministic Logistics analysis engine (Phase 9).

Every exact-value assertion here was first computed by running the real
implementation directly (see conversation/dev notes) and only then copied
into an assertion -- never hand-derived and assumed correct.
"""

from decimal import Decimal

import pytest

from src.logistics_analysis import (
    EVIDENCE_WEIGHTS,
    _interpolate,
    analyze_logistics,
)
from src.logistics_models import LogisticsInputs


def _phone_case(**overrides):
    base = dict(
        product_name="Phone case",
        weight_kg=Decimal("0.1"),
        length_cm=Decimal("15"),
        width_cm=Decimal("8"),
        height_cm=Decimal("1"),
        fragile=False,
        requires_special_handling=False,
        estimated_delivery_days=2,
        supplier_fulfilled=True,
        tracking_available=True,
        insurance_available=True,
        liquid=False,
        hazardous=False,
        perishable=False,
        temperature_sensitive=False,
        stackable=True,
    )
    base.update(overrides)
    return LogisticsInputs(**base)


def _mirror(**overrides):
    base = dict(
        product_name="Mirror",
        weight_kg=Decimal("12"),
        length_cm=Decimal("100"),
        width_cm=Decimal("60"),
        height_cm=Decimal("5"),
        fragile=True,
        requires_special_handling=True,
        estimated_delivery_days=8,
        liquid=False,
        hazardous=False,
        perishable=False,
        temperature_sensitive=False,
        stackable=False,
        supplier_fulfilled=False,
        tracking_available=True,
        insurance_available=True,
    )
    base.update(overrides)
    return LogisticsInputs(**base)


# -- Evidence weights sanity --------------------------------------------------


def test_evidence_weights_sum_to_one():
    assert sum(EVIDENCE_WEIGHTS.values()) == pytest.approx(1.0)


# -- Easy/light vs difficult/heavy worked example -----------------------------


def test_easy_light_product_phone_case():
    result = analyze_logistics(_phone_case())
    assert result.logistics_score == 100.0
    assert result.operational_status == "EASY"
    assert result.physical_ease_score == 100.0
    assert result.handling_ease_score == 100.0
    assert result.delivery_convenience_score == 100.0
    assert result.fulfillment_support_score == 100.0
    assert result.shipping_support_score == 100.0


def test_difficult_heavy_product_mirror():
    result = analyze_logistics(_mirror())
    assert result.logistics_score == 64.51
    assert result.operational_status == "MANAGEABLE"
    assert result.physical_ease_score == 41.0
    assert result.delivery_convenience_score == 70.0
    assert result.fulfillment_support_score == 60.0
    assert result.shipping_support_score == 100.0


def test_phone_case_scores_higher_than_mirror_despite_identical_margin_relevance():
    phone_result = analyze_logistics(_phone_case())
    mirror_result = analyze_logistics(_mirror())
    assert phone_result.logistics_score > mirror_result.logistics_score


# -- Handling flags: True / False / None each matter --------------------------


@pytest.mark.parametrize("value", [True, False, None])
def test_fragile_true_false_none_all_accepted_and_distinct(value):
    result = analyze_logistics(_phone_case(fragile=value))
    assert result.observed["fragile"] is value


def test_fragile_true_lowers_handling_ease_vs_false():
    fragile_true = analyze_logistics(_phone_case(fragile=True))
    fragile_false = analyze_logistics(_phone_case(fragile=False))
    assert fragile_true.handling_ease_score < fragile_false.handling_ease_score


def test_fragile_none_excluded_not_penalized():
    with_false = analyze_logistics(_phone_case(fragile=False, liquid=False, hazardous=False, perishable=False, temperature_sensitive=False, stackable=True, requires_special_handling=False))
    with_none = analyze_logistics(_phone_case(fragile=None, liquid=False, hazardous=False, perishable=False, temperature_sensitive=False, stackable=True, requires_special_handling=False))
    assert with_none.handling_ease_score is not None
    assert with_none.evidence_completeness_score < with_false.evidence_completeness_score


@pytest.mark.parametrize(
    "field",
    ["liquid", "hazardous", "perishable", "temperature_sensitive", "stackable", "requires_special_handling"],
)
@pytest.mark.parametrize("value", [True, False, None])
def test_handling_flags_accept_true_false_none(field, value):
    result = analyze_logistics(_phone_case(**{field: value}))
    assert result.observed[field] is value


# -- Dimensions / volume -------------------------------------------------------


def test_all_three_dimensions_known_computes_volume():
    result = analyze_logistics(_phone_case())
    assert result.package_volume_cm3 == 120
    assert result.volume_liters == Decimal("0.12")


def test_missing_one_dimension_means_no_volume():
    inputs = LogisticsInputs(product_name="Item", length_cm=Decimal("10"), width_cm=Decimal("10"))
    result = analyze_logistics(inputs)
    assert result.package_volume_cm3 is None
    assert result.physical_ease_score is None


def test_all_dimensions_missing_means_no_volume():
    inputs = LogisticsInputs(product_name="Item", weight_kg=Decimal("1"))
    result = analyze_logistics(inputs)
    assert result.package_volume_cm3 is None


def test_volume_cm3_and_liters_are_not_the_same_unit():
    result = analyze_logistics(_mirror())
    assert result.package_volume_cm3 == 30000
    assert result.volume_liters == 30
    assert result.package_volume_cm3 != result.volume_liters


# -- Dimensional weight / reference billable weight ---------------------------


def test_dimensional_weight_requires_explicit_divisor():
    without_divisor = LogisticsInputs(
        product_name="Item", weight_kg=Decimal("1"),
        length_cm=Decimal("50"), width_cm=Decimal("50"), height_cm=Decimal("50"),
    )
    result = analyze_logistics(without_divisor)
    assert result.dimensional_weight_kg is None
    assert result.reference_billable_weight_kg is None


def test_dimensional_weight_computed_when_divisor_supplied():
    with_divisor = LogisticsInputs(
        product_name="Item", weight_kg=Decimal("1"),
        length_cm=Decimal("50"), width_cm=Decimal("50"), height_cm=Decimal("50"),
        dimensional_weight_divisor=Decimal("5000"),
    )
    result = analyze_logistics(with_divisor)
    assert result.dimensional_weight_kg == 25
    assert result.reference_billable_weight_kg == 25


def test_dimensional_weight_warning_never_coalesces_missing_weight_to_zero():
    """Regression: the dimensional-weight-exceeds-actual-weight warning check
    must never treat a missing weight_kg as 0 -- it should simply not fire,
    not compare against a fabricated zero."""
    volume_only = LogisticsInputs(
        product_name="No weight known",
        length_cm=Decimal("50"), width_cm=Decimal("50"), height_cm=Decimal("50"),
        dimensional_weight_divisor=Decimal("5000"),
    )
    result = analyze_logistics(volume_only)
    assert result.reference_billable_weight_kg is None
    assert not any("dimensional weight exceeds actual weight" in w for w in result.warnings)


def test_dimensional_weight_exceeding_actual_weight_produces_warning_not_blocker():
    with_divisor = LogisticsInputs(
        product_name="Item", weight_kg=Decimal("1"),
        length_cm=Decimal("50"), width_cm=Decimal("50"), height_cm=Decimal("50"),
        dimensional_weight_divisor=Decimal("5000"),
    )
    result = analyze_logistics(with_divisor)
    assert any("dimensional weight exceeds actual weight" in w for w in result.warnings)
    assert result.blockers == []


# -- Delivery days --------------------------------------------------------------


def test_fast_delivery_scores_higher_than_slow_delivery():
    fast = analyze_logistics(_phone_case(estimated_delivery_days=2))
    slow = analyze_logistics(_phone_case(estimated_delivery_days=25))
    assert fast.delivery_convenience_score > slow.delivery_convenience_score


def test_unknown_delivery_days_excluded_from_dimension():
    result = analyze_logistics(_phone_case(estimated_delivery_days=None))
    assert result.observed["estimated_delivery_days"] is None


# -- Tracking / insurance / fulfillment -----------------------------------------


@pytest.mark.parametrize("value", [True, False, None])
def test_tracking_available_true_false_none(value):
    result = analyze_logistics(_phone_case(tracking_available=value))
    assert result.observed["tracking_available"] is value


@pytest.mark.parametrize("value", [True, False, None])
def test_insurance_available_true_false_none(value):
    result = analyze_logistics(_phone_case(insurance_available=value))
    assert result.observed["insurance_available"] is value


def test_supplier_fulfilled_true_scores_higher_than_false():
    supplier = analyze_logistics(_phone_case(supplier_fulfilled=True, seller_fulfilled=None, warehouse_required=None))
    not_supplier = analyze_logistics(_phone_case(supplier_fulfilled=False, seller_fulfilled=None, warehouse_required=None))
    assert supplier.fulfillment_support_score > not_supplier.fulfillment_support_score


def test_warehouse_required_true_scores_lower_than_false():
    warehouse = analyze_logistics(_phone_case(supplier_fulfilled=None, seller_fulfilled=None, warehouse_required=True))
    no_warehouse = analyze_logistics(_phone_case(supplier_fulfilled=None, seller_fulfilled=None, warehouse_required=False))
    assert warehouse.fulfillment_support_score < no_warehouse.fulfillment_support_score


# -- Shipping cost: zero vs None -------------------------------------------------


def test_known_shipping_cost_zero_is_distinct_from_none():
    zero = analyze_logistics(_phone_case(known_shipping_cost=Decimal("0")))
    unknown = analyze_logistics(_phone_case(known_shipping_cost=None))
    assert zero.observed["known_shipping_cost"] == Decimal("0")
    assert zero.observed["known_shipping_cost"] is not None
    assert unknown.observed["known_shipping_cost"] is None


# -- Damage / return rate: observed vs inferred, blockers ------------------------


def test_damage_rate_zero_is_distinct_from_none():
    zero = analyze_logistics(_phone_case(observed_damage_rate=Decimal("0")))
    unknown = analyze_logistics(_phone_case(observed_damage_rate=None))
    assert zero.observed["observed_damage_rate"] == Decimal("0")
    assert unknown.observed["observed_damage_rate"] is None


def test_return_rate_zero_is_distinct_from_none():
    zero = analyze_logistics(_phone_case(observed_return_rate=Decimal("0")))
    unknown = analyze_logistics(_phone_case(observed_return_rate=None))
    assert zero.observed["observed_return_rate"] == Decimal("0")
    assert unknown.observed["observed_return_rate"] is None


def test_damage_rate_at_or_above_half_is_not_a_blocker_but_a_severe_warning():
    """A 60% observed damage rate is extremely bad operational evidence, but
    the 40% of shipments that were NOT damaged are direct proof fulfillment
    is not physically impossible -- so this must never reach BLOCKED. It
    forces CAUTION and produces a severe warning instead."""
    result = analyze_logistics(LogisticsInputs(product_name="Risky item", observed_damage_rate=Decimal("0.6")))
    assert result.operational_status != "BLOCKED"
    assert result.operational_status == "CAUTION"
    assert result.blockers == []
    assert any("severe negative operational evidence" in w for w in result.warnings)
    assert any("does NOT by itself prove fulfillment is impossible" in w for w in result.warnings)


def test_return_rate_at_or_above_half_is_not_a_blocker_but_a_severe_warning():
    result = analyze_logistics(LogisticsInputs(product_name="Returned item", observed_return_rate=Decimal("0.55")))
    assert result.operational_status != "BLOCKED"
    assert result.operational_status == "CAUTION"
    assert result.blockers == []
    assert any("severe negative operational evidence" in w for w in result.warnings)


def test_damage_rate_below_half_is_not_a_blocker_and_not_a_severe_warning():
    result = analyze_logistics(LogisticsInputs(product_name="Low damage item", observed_damage_rate=Decimal("0.05")))
    assert result.blockers == []
    assert result.warnings == []


def test_explicit_zero_damage_rate_is_positive_evidence_and_produces_no_warning():
    """Explicit zero is strong POSITIVE evidence (every observed shipment
    arrived fine) and must never be confused with `None` (unknown) -- neither
    should ever produce a severe-rate warning."""
    result = analyze_logistics(_phone_case(observed_damage_rate=Decimal("0"), observed_return_rate=Decimal("0")))
    assert result.observed["observed_damage_rate"] == Decimal("0")
    assert result.warnings == []
    assert result.operational_status == "EASY"


def test_fragile_true_never_fabricates_a_damage_probability():
    result = analyze_logistics(_phone_case(fragile=True))
    assert "observed_damage_rate" not in result.derived
    assert any("damage probability" in item for item in result.unavailable)


def test_no_current_input_combination_produces_blocked():
    """Per the Phase 9 hardening review: no field in the current
    LogisticsInputs schema can prove a genuine operational impossibility, so
    BLOCKED must be unreachable today -- this guards against a future change
    accidentally resurrecting the severe-rate-as-blocker bug."""
    worst_case = LogisticsInputs(
        product_name="Worst plausible case",
        weight_kg=Decimal("50"),
        length_cm=Decimal("150"), width_cm=Decimal("150"), height_cm=Decimal("150"),
        fragile=True, liquid=True, hazardous=True, perishable=True, temperature_sensitive=True,
        stackable=False, requires_special_handling=True, extra_packaging_required=True,
        packaging_cost=Decimal("50"), supplier_fulfilled=False, seller_fulfilled=False,
        warehouse_required=True, known_shipping_cost=Decimal("200"), estimated_delivery_days=60,
        tracking_available=False, insurance_available=False,
        observed_damage_rate=Decimal("1"), observed_return_rate=Decimal("1"),
    )
    result = analyze_logistics(worst_case)
    assert result.blockers == []
    assert result.operational_status != "BLOCKED"
    assert result.operational_status == "CAUTION"


def test_severe_warning_shown_alongside_score_not_hidden_inside_it():
    """A severe observed-rate warning is shown ALONGSIDE the score, never
    hidden inside the weighted average, and never silently forces the score
    to `None` by itself -- the score still reflects the OTHER, independent
    dimensions (physical/handling/delivery/etc.). A high score next to
    `Operational Status: CAUTION` is honest, not a bug: it means "the parts
    we could measure looked fine, but a real observed failure rate still
    makes this operation risky."
    """
    inputs = LogisticsInputs(
        product_name="Damaged goods, high completeness",
        weight_kg=Decimal("1"),
        length_cm=Decimal("10"), width_cm=Decimal("10"), height_cm=Decimal("10"),
        fragile=False, liquid=False, hazardous=False, perishable=False, temperature_sensitive=False,
        stackable=True, requires_special_handling=False, extra_packaging_required=False,
        packaging_cost=Decimal("1"), supplier_fulfilled=True, seller_fulfilled=True, warehouse_required=False,
        known_shipping_cost=Decimal("10"), estimated_delivery_days=3, tracking_available=True, insurance_available=True,
        observed_damage_rate=Decimal("0.9"), observed_return_rate=Decimal("0.1"),
    )
    result = analyze_logistics(inputs)
    assert result.operational_status == "CAUTION"
    assert result.blockers == []
    assert result.logistics_score == 94.52
    assert any("severe negative operational evidence" in w for w in result.warnings)


def test_severe_warning_with_low_completeness_still_surfaces_caution_not_insufficient_data():
    """Even when most other fields are unknown, a severe observed rate is
    concrete, specific evidence in its own right -- it must not be buried
    under a generic INSUFFICIENT_DATA status. logistics_score is still
    withheld independently, because overall evidence completeness has
    nothing to do with how the observed-rate warning is surfaced."""
    inputs = LogisticsInputs(
        product_name="Damaged goods, sparse",
        weight_kg=Decimal("1"),
        length_cm=Decimal("10"), width_cm=Decimal("10"), height_cm=Decimal("10"),
        fragile=True,
        observed_damage_rate=Decimal("0.9"),
    )
    result = analyze_logistics(inputs)
    assert result.operational_status == "CAUTION"
    assert result.blockers == []
    assert result.logistics_score is None
    assert result.evidence_completeness_score < 40.0


# -- Evidence completeness: independent from score -------------------------------


def test_evidence_completeness_independent_from_logistics_score():
    full_but_bad = LogisticsInputs(
        product_name="Full info bad product", weight_kg=Decimal("25"),
        length_cm=Decimal("90"), width_cm=Decimal("90"), height_cm=Decimal("90"),
        fragile=True, liquid=True, hazardous=True, perishable=True, temperature_sensitive=True,
        stackable=False, requires_special_handling=True, extra_packaging_required=True,
        packaging_cost=Decimal("20"), supplier_fulfilled=False, seller_fulfilled=False,
        warehouse_required=True, known_shipping_cost=Decimal("80"), estimated_delivery_days=25,
        tracking_available=False, insurance_available=False,
        observed_damage_rate=Decimal("0.3"), observed_return_rate=Decimal("0.2"),
    )
    result = analyze_logistics(full_but_bad)
    assert result.evidence_completeness_score == 100.0
    assert result.logistics_score == 23.03
    assert result.operational_status == "CAUTION"


def test_sparse_data_below_completeness_threshold_withholds_score():
    result = analyze_logistics(LogisticsInputs(product_name="Sparse item", fragile=True))
    assert result.logistics_score is None
    assert result.operational_status == "INSUFFICIENT_DATA"


def test_minimal_inputs_score_withheld():
    result = analyze_logistics(LogisticsInputs(product_name="Mystery item"))
    assert result.logistics_score is None
    assert result.evidence_completeness_score == 0.0
    assert result.operational_status == "INSUFFICIENT_DATA"


# -- Missing dimensions excluded, weights renormalize -----------------------------


def test_missing_dimensions_excluded_from_physical_ease():
    weight_only = LogisticsInputs(product_name="Weight only", weight_kg=Decimal("2"))
    result = analyze_logistics(weight_only)
    assert result.physical_ease_score is not None
    assert result.package_volume_cm3 is None


# -- Determinism and score bounds --------------------------------------------------


def test_identical_inputs_produce_identical_results():
    first = analyze_logistics(_mirror())
    second = analyze_logistics(_mirror())
    assert first.logistics_score == second.logistics_score
    assert first.evidence_completeness_score == second.evidence_completeness_score
    assert first.operational_status == second.operational_status


@pytest.mark.parametrize("builder", [_phone_case, _mirror])
def test_score_within_bounds(builder):
    result = analyze_logistics(builder())
    assert 0.0 <= result.logistics_score <= 100.0
    assert 0.0 <= result.evidence_completeness_score <= 100.0


# -- No duplication of Supplier or Margin analysis ---------------------------------


def test_no_sale_price_field_so_no_margin_logic_possible():
    inputs = _phone_case()
    assert not hasattr(inputs, "sale_price")


def test_estimated_delivery_days_is_not_treated_as_supplier_lead_time():
    result = analyze_logistics(_phone_case(estimated_delivery_days=2))
    assert "lead_time_days" not in result.observed
    assert "dispatch_time_days" not in result.observed


def test_known_shipping_cost_never_produces_a_profit_or_margin_field():
    result = analyze_logistics(_phone_case(known_shipping_cost=Decimal("10")))
    for attr in ("profit", "margin", "contribution_profit", "contribution_margin"):
        assert not hasattr(result, attr)


# -- Interpolation helper sanity ----------------------------------------------------


def test_interpolate_exact_anchor_matches():
    anchors = ((0.5, 100.0), (1, 90.0), (5, 65.0))
    assert _interpolate(0.5, anchors) == 100.0
    assert _interpolate(1, anchors) == 90.0


def test_interpolate_beyond_last_anchor_clamps():
    anchors = ((0.5, 100.0), (1, 90.0), (5, 65.0))
    assert _interpolate(100, anchors) == 65.0


def test_interpolate_before_first_anchor_clamps():
    anchors = ((0.5, 100.0), (1, 90.0), (5, 65.0))
    assert _interpolate(0.1, anchors) == 100.0
