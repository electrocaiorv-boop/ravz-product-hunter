"""Tests for the provider-neutral LogisticsInputs model (Phase 9)."""

from decimal import Decimal

import pytest

from src.logistics_models import LogisticsInputs


def test_minimal_valid_construction_only_product_name():
    inputs = LogisticsInputs(product_name="Phone case")
    assert inputs.product_name == "Phone case"
    assert inputs.weight_kg is None
    assert inputs.fragile is None
    assert inputs.estimated_delivery_days is None


def test_empty_product_name_rejected():
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="")


def test_blank_product_name_rejected():
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="   ")


@pytest.mark.parametrize("field", ["weight_kg", "length_cm", "width_cm", "height_cm", "dimensional_weight_divisor"])
def test_zero_measure_fields_rejected(field):
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", **{field: Decimal("0")})


@pytest.mark.parametrize("field", ["weight_kg", "length_cm", "width_cm", "height_cm", "dimensional_weight_divisor"])
def test_negative_measure_fields_rejected(field):
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", **{field: Decimal("-1")})


@pytest.mark.parametrize("field", ["weight_kg", "length_cm", "width_cm", "height_cm", "dimensional_weight_divisor"])
def test_positive_measure_fields_accepted(field):
    inputs = LogisticsInputs(product_name="Item", **{field: Decimal("5")})
    assert getattr(inputs, field) == Decimal("5")


def test_negative_packaging_cost_rejected():
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", packaging_cost=Decimal("-1"))


def test_negative_known_shipping_cost_rejected():
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", known_shipping_cost=Decimal("-1"))


def test_zero_packaging_cost_is_valid_and_distinct_from_none():
    inputs = LogisticsInputs(product_name="Item", packaging_cost=Decimal("0"))
    assert inputs.packaging_cost == Decimal("0")
    assert inputs.packaging_cost is not None


def test_zero_known_shipping_cost_is_valid_and_distinct_from_none():
    inputs = LogisticsInputs(product_name="Item", known_shipping_cost=Decimal("0"))
    assert inputs.known_shipping_cost == Decimal("0")
    assert inputs.known_shipping_cost is not None


def test_negative_estimated_delivery_days_rejected():
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", estimated_delivery_days=-1)


def test_zero_estimated_delivery_days_is_valid():
    inputs = LogisticsInputs(product_name="Item", estimated_delivery_days=0)
    assert inputs.estimated_delivery_days == 0


@pytest.mark.parametrize("field", ["observed_damage_rate", "observed_return_rate"])
def test_rate_fields_below_zero_rejected(field):
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", **{field: Decimal("-0.1")})


@pytest.mark.parametrize("field", ["observed_damage_rate", "observed_return_rate"])
def test_rate_fields_above_one_rejected(field):
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", **{field: Decimal("1.1")})


@pytest.mark.parametrize("field", ["observed_damage_rate", "observed_return_rate"])
def test_rate_fields_boundary_values_accepted(field):
    low = LogisticsInputs(product_name="Item", **{field: Decimal("0")})
    high = LogisticsInputs(product_name="Item", **{field: Decimal("1")})
    assert getattr(low, field) == Decimal("0")
    assert getattr(high, field) == Decimal("1")


def test_zero_observed_rate_is_valid_and_distinct_from_none():
    inputs = LogisticsInputs(product_name="Item", observed_damage_rate=Decimal("0"))
    assert inputs.observed_damage_rate == Decimal("0")
    assert inputs.observed_damage_rate is not None


@pytest.mark.parametrize(
    "field",
    [
        "fragile",
        "liquid",
        "hazardous",
        "perishable",
        "temperature_sensitive",
        "stackable",
        "requires_special_handling",
        "extra_packaging_required",
        "supplier_fulfilled",
        "seller_fulfilled",
        "warehouse_required",
        "tracking_available",
        "insurance_available",
    ],
)
def test_boolean_fields_accept_true_false_and_none(field):
    true_inputs = LogisticsInputs(product_name="Item", **{field: True})
    false_inputs = LogisticsInputs(product_name="Item", **{field: False})
    none_inputs = LogisticsInputs(product_name="Item")
    assert getattr(true_inputs, field) is True
    assert getattr(false_inputs, field) is False
    assert getattr(none_inputs, field) is None


@pytest.mark.parametrize(
    "field",
    [
        "fragile",
        "liquid",
        "hazardous",
        "perishable",
        "temperature_sensitive",
        "stackable",
        "requires_special_handling",
        "extra_packaging_required",
        "supplier_fulfilled",
        "seller_fulfilled",
        "warehouse_required",
        "tracking_available",
        "insurance_available",
    ],
)
def test_boolean_fields_reject_non_bool_values(field):
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", **{field: "yes"})


def test_decimal_fields_coerce_from_str():
    inputs = LogisticsInputs(product_name="Item", weight_kg="2.5")
    assert inputs.weight_kg == Decimal("2.5")


def test_decimal_fields_coerce_from_int():
    inputs = LogisticsInputs(product_name="Item", weight_kg=3)
    assert inputs.weight_kg == Decimal("3")


def test_decimal_fields_reject_non_numeric_string():
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", weight_kg="not-a-number")


def test_estimated_delivery_days_coerces_from_str():
    inputs = LogisticsInputs(product_name="Item", estimated_delivery_days="5")
    assert inputs.estimated_delivery_days == 5


def test_estimated_delivery_days_rejects_bool():
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", estimated_delivery_days=True)


def test_estimated_delivery_days_rejects_non_numeric_string():
    with pytest.raises(ValueError):
        LogisticsInputs(product_name="Item", estimated_delivery_days="soon")


def test_no_sale_price_field_exists():
    inputs = LogisticsInputs(product_name="Item")
    assert not hasattr(inputs, "sale_price")


def test_partial_dimensions_construct_without_error():
    inputs = LogisticsInputs(product_name="Item", length_cm=Decimal("10"), width_cm=Decimal("10"))
    assert inputs.length_cm == Decimal("10")
    assert inputs.height_cm is None
