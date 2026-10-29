from decimal import Decimal

import pytest

from src.supplier_models import SupplierInputs


def make_inputs(**overrides):
    base = dict(product_name="Bebedouro", supplier_name="Fornecedor A")
    base.update(overrides)
    return SupplierInputs(**base)


def test_minimal_valid_construction():
    inputs = make_inputs()
    assert inputs.product_name == "Bebedouro"
    assert inputs.supplier_name == "Fornecedor A"
    assert inputs.moq_units is None
    assert inputs.stock_available is None


def test_empty_product_name_rejected():
    with pytest.raises(ValueError):
        make_inputs(product_name="   ")


def test_empty_supplier_name_rejected():
    with pytest.raises(ValueError):
        make_inputs(supplier_name="")


def test_moq_below_one_rejected():
    with pytest.raises(ValueError):
        make_inputs(moq_units=0)


def test_moq_of_one_is_allowed():
    inputs = make_inputs(moq_units=1)
    assert inputs.moq_units == 1


def test_minimum_order_value_must_be_positive():
    with pytest.raises(ValueError):
        make_inputs(minimum_order_value=Decimal("0"))
    with pytest.raises(ValueError):
        make_inputs(minimum_order_value=Decimal("-5"))
    inputs = make_inputs(minimum_order_value=Decimal("100"))
    assert inputs.minimum_order_value == Decimal("100")


@pytest.mark.parametrize("field", ["unit_cost", "shipping_cost"])
def test_negative_money_rejected(field):
    with pytest.raises(ValueError):
        make_inputs(**{field: Decimal("-1")})


@pytest.mark.parametrize(
    "field",
    [
        "payment_terms_days",
        "stock_quantity",
        "dispatch_time_days",
        "delivery_time_days",
        "lead_time_days",
        "review_count",
        "years_active",
    ],
)
def test_negative_day_or_count_fields_rejected(field):
    with pytest.raises(ValueError):
        make_inputs(**{field: -1})


def test_supplier_rating_out_of_range_rejected():
    with pytest.raises(ValueError):
        make_inputs(supplier_rating=Decimal("5.1"))
    with pytest.raises(ValueError):
        make_inputs(supplier_rating=Decimal("-0.1"))


def test_supplier_rating_boundary_values_accepted():
    make_inputs(supplier_rating=Decimal("0"))
    make_inputs(supplier_rating=Decimal("5"))


def test_lead_time_with_both_dispatch_and_delivery_conflict_rejected():
    with pytest.raises(ValueError):
        make_inputs(lead_time_days=10, dispatch_time_days=2, delivery_time_days=8)


def test_lead_time_with_only_dispatch_is_not_a_conflict():
    """Only ONE of dispatch/delivery alongside explicit lead_time is extra detail, not a conflict."""
    inputs = make_inputs(lead_time_days=10, dispatch_time_days=2)
    assert inputs.lead_time_days == 10
    assert inputs.dispatch_time_days == 2


def test_dispatch_and_delivery_without_explicit_lead_time_is_allowed():
    inputs = make_inputs(dispatch_time_days=2, delivery_time_days=5)
    assert inputs.dispatch_time_days == 2
    assert inputs.delivery_time_days == 5
    assert inputs.lead_time_days is None


@pytest.mark.parametrize(
    "field",
    [
        "stock_available",
        "tracking_available",
        "dropshipping_supported",
        "blind_shipping_supported",
        "invoice_available",
        "return_policy_available",
        "business_verified",
        "contact_available",
    ],
)
def test_bool_fields_reject_non_boolean_values(field):
    with pytest.raises(ValueError):
        make_inputs(**{field: "yes"})


@pytest.mark.parametrize(
    "field",
    [
        "stock_available",
        "tracking_available",
        "dropshipping_supported",
        "blind_shipping_supported",
        "invoice_available",
        "return_policy_available",
        "business_verified",
        "contact_available",
    ],
)
def test_bool_fields_preserve_tristate(field):
    true_inputs = make_inputs(**{field: True})
    false_inputs = make_inputs(**{field: False})
    none_inputs = make_inputs()

    assert getattr(true_inputs, field) is True
    assert getattr(false_inputs, field) is False
    assert getattr(none_inputs, field) is None


def test_stock_quantity_below_moq_is_allowed_to_construct():
    """A real, analyzable business condition -- not an input ambiguity to reject."""
    inputs = make_inputs(moq_units=100, stock_quantity=5)
    assert inputs.moq_units == 100
    assert inputs.stock_quantity == 5


def test_decimal_and_int_coercion_from_str_and_float():
    inputs = make_inputs(
        unit_cost="10.50",
        moq_units="20",
        supplier_rating=4.5,
    )
    assert inputs.unit_cost == Decimal("10.50")
    assert inputs.moq_units == 20
    assert inputs.supplier_rating == Decimal("4.5")
