"""Tests for the provider-neutral RiskInputs model (Phase 10)."""

from decimal import Decimal

import pytest

from src.risk_models import RiskInputs


def test_minimal_valid_construction_only_product_name():
    inputs = RiskInputs(product_name="Widget")
    assert inputs.product_name == "Widget"
    assert inputs.supplier_count is None
    assert inputs.regulatory_uncertainty is None


def test_empty_product_name_rejected():
    with pytest.raises(ValueError):
        RiskInputs(product_name="")


def test_blank_product_name_rejected():
    with pytest.raises(ValueError):
        RiskInputs(product_name="   ")


def test_negative_supplier_count_rejected():
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", supplier_count=-1)


def test_zero_supplier_count_is_valid_and_distinct_from_none():
    inputs = RiskInputs(product_name="Widget", supplier_count=0)
    assert inputs.supplier_count == 0
    assert inputs.supplier_count is not None


def test_supplier_count_coerces_from_str():
    inputs = RiskInputs(product_name="Widget", supplier_count="5")
    assert inputs.supplier_count == 5


def test_supplier_count_rejects_bool():
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", supplier_count=True)


def test_supplier_count_rejects_non_numeric_string():
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", supplier_count="many")


@pytest.mark.parametrize(
    "field",
    [
        "primary_supplier_dependency_percent",
        "platform_dependency_percent",
        "advertising_dependency_percent",
        "observed_price_volatility_percent",
        "historical_stockout_rate",
        "observed_return_rate",
        "observed_damage_rate",
    ],
)
def test_rate_fields_below_zero_rejected(field):
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", **{field: Decimal("-0.1")})


@pytest.mark.parametrize(
    "field",
    [
        "primary_supplier_dependency_percent",
        "platform_dependency_percent",
        "advertising_dependency_percent",
        "observed_price_volatility_percent",
        "historical_stockout_rate",
        "observed_return_rate",
        "observed_damage_rate",
    ],
)
def test_rate_fields_above_one_rejected(field):
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", **{field: Decimal("1.1")})


@pytest.mark.parametrize(
    "field",
    [
        "primary_supplier_dependency_percent",
        "platform_dependency_percent",
        "advertising_dependency_percent",
        "observed_price_volatility_percent",
        "historical_stockout_rate",
        "observed_return_rate",
        "observed_damage_rate",
    ],
)
def test_rate_fields_boundary_values_accepted(field):
    low = RiskInputs(product_name="Widget", **{field: Decimal("0")})
    high = RiskInputs(product_name="Widget", **{field: Decimal("1")})
    assert getattr(low, field) == Decimal("0")
    assert getattr(high, field) == Decimal("1")


def test_zero_rate_is_valid_and_distinct_from_none():
    inputs = RiskInputs(product_name="Widget", observed_return_rate=Decimal("0"))
    assert inputs.observed_return_rate == Decimal("0")
    assert inputs.observed_return_rate is not None


def test_rate_fields_coerce_from_str_and_float():
    from_str = RiskInputs(product_name="Widget", observed_return_rate="0.25")
    from_float = RiskInputs(product_name="Widget", observed_damage_rate=0.1)
    assert from_str.observed_return_rate == Decimal("0.25")
    assert from_float.observed_damage_rate == Decimal("0.1")


def test_negative_seasonality_level_rejected():
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", seasonality_level=-1)


def test_seasonality_level_above_100_rejected():
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", seasonality_level=101)


def test_seasonality_level_boundary_values_accepted():
    low = RiskInputs(product_name="Widget", seasonality_level=0)
    high = RiskInputs(product_name="Widget", seasonality_level=100)
    assert low.seasonality_level == 0
    assert high.seasonality_level == 100


def test_seasonality_level_is_not_a_0_1_rate():
    """0.8 on the 0-100 scale means 0.8, NOT 80 -- this field is never
    silently treated as a fraction the way the rate fields are."""
    inputs = RiskInputs(product_name="Widget", seasonality_level=80)
    assert inputs.seasonality_level == 80
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", seasonality_level=150)


@pytest.mark.parametrize(
    "field",
    [
        "regulatory_uncertainty",
        "brand_ip_uncertainty",
        "recall_history_present",
        "replacement_supplier_available",
        "alternative_fulfillment_available",
    ],
)
def test_boolean_fields_accept_true_false_and_none(field):
    true_inputs = RiskInputs(product_name="Widget", **{field: True})
    false_inputs = RiskInputs(product_name="Widget", **{field: False})
    none_inputs = RiskInputs(product_name="Widget")
    assert getattr(true_inputs, field) is True
    assert getattr(false_inputs, field) is False
    assert getattr(none_inputs, field) is None


@pytest.mark.parametrize(
    "field",
    [
        "regulatory_uncertainty",
        "brand_ip_uncertainty",
        "recall_history_present",
        "replacement_supplier_available",
        "alternative_fulfillment_available",
    ],
)
def test_boolean_fields_reject_non_bool_values(field):
    with pytest.raises(ValueError):
        RiskInputs(product_name="Widget", **{field: "yes"})


def test_supplier_count_and_primary_dependency_percent_may_coexist():
    """Section 8: these are complementary signals, not an ambiguous dual
    representation -- construction must never reject this combination."""
    inputs = RiskInputs(
        product_name="Widget", supplier_count=5, primary_supplier_dependency_percent=Decimal("0.95")
    )
    assert inputs.supplier_count == 5
    assert inputs.primary_supplier_dependency_percent == Decimal("0.95")


def test_no_sale_price_or_margin_field_exists():
    inputs = RiskInputs(product_name="Widget")
    assert not hasattr(inputs, "sale_price")
    assert not hasattr(inputs, "margin")
