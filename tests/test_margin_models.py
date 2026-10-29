from decimal import Decimal

import pytest

from src.margin_models import MarginInputs


def make_inputs(**overrides):
    base = dict(product_name="Bebedouro", sale_price=Decimal("100"), product_cost=Decimal("50"))
    base.update(overrides)
    return MarginInputs(**base)


def test_minimal_valid_construction():
    inputs = make_inputs()
    assert inputs.sale_price == Decimal("100")
    assert inputs.product_cost == Decimal("50")
    assert inputs.marketplace_fee_amount is None
    assert inputs.marketplace_fee_rate is None


def test_zero_sale_price_rejected():
    with pytest.raises(ValueError):
        make_inputs(sale_price=Decimal("0"))


def test_negative_sale_price_rejected():
    with pytest.raises(ValueError):
        make_inputs(sale_price=Decimal("-10"))


def test_zero_product_cost_is_allowed():
    """Edge case: a free/digital product may legitimately cost 0."""
    inputs = make_inputs(product_cost=Decimal("0"))
    assert inputs.product_cost == Decimal("0")


def test_negative_product_cost_rejected():
    with pytest.raises(ValueError):
        make_inputs(product_cost=Decimal("-1"))


@pytest.mark.parametrize(
    "field",
    [
        "marketplace_fee_amount",
        "fixed_marketplace_fee",
        "seller_shipping_cost",
        "packaging_cost",
        "tax_amount",
        "payment_cost",
        "advertising_cost_per_sale",
        "return_reserve",
        "other_variable_cost",
    ],
)
def test_negative_optional_money_rejected(field):
    with pytest.raises(ValueError):
        make_inputs(**{field: Decimal("-1")})


@pytest.mark.parametrize("field", ["marketplace_fee_rate", "tax_rate"])
def test_rate_out_of_range_rejected(field):
    with pytest.raises(ValueError):
        make_inputs(**{field: Decimal("1.5")})
    with pytest.raises(ValueError):
        make_inputs(**{field: Decimal("-0.1")})


@pytest.mark.parametrize("field", ["marketplace_fee_rate", "tax_rate"])
def test_rate_boundary_values_accepted(field):
    make_inputs(**{field: Decimal("0")})
    make_inputs(**{field: Decimal("1")})


def test_marketplace_fee_amount_and_rate_conflict_rejected():
    with pytest.raises(ValueError):
        make_inputs(marketplace_fee_amount=Decimal("10"), marketplace_fee_rate=Decimal("0.1"))


def test_marketplace_fee_amount_and_fixed_fee_conflict_rejected():
    with pytest.raises(ValueError):
        make_inputs(marketplace_fee_amount=Decimal("10"), fixed_marketplace_fee=Decimal("2"))


def test_marketplace_fee_rate_and_fixed_fee_may_coexist():
    """Not a conflict: a percentage fee plus an additional flat fee is a real structure."""
    inputs = make_inputs(marketplace_fee_rate=Decimal("0.12"), fixed_marketplace_fee=Decimal("3"))
    assert inputs.marketplace_fee_rate == Decimal("0.12")
    assert inputs.fixed_marketplace_fee == Decimal("3")


def test_tax_amount_and_rate_conflict_rejected():
    with pytest.raises(ValueError):
        make_inputs(tax_amount=Decimal("5"), tax_rate=Decimal("0.06"))


def test_decimal_coercion_from_int_float_str():
    inputs = make_inputs(
        sale_price=100,
        product_cost="50.5",
        seller_shipping_cost=10.0,
    )
    assert inputs.sale_price == Decimal("100")
    assert inputs.product_cost == Decimal("50.5")
    assert inputs.seller_shipping_cost == Decimal("10.0")


def test_float_coercion_avoids_binary_representation_error():
    """Decimal(str(0.1)) must be exact; Decimal(0.1) directly would not be."""
    inputs = make_inputs(seller_shipping_cost=0.1)
    assert inputs.seller_shipping_cost == Decimal("0.1")


def test_blank_optional_fields_stay_none():
    inputs = make_inputs()
    for field in (
        "marketplace_fee_amount",
        "marketplace_fee_rate",
        "fixed_marketplace_fee",
        "seller_shipping_cost",
        "packaging_cost",
        "tax_amount",
        "tax_rate",
        "payment_cost",
        "advertising_cost_per_sale",
        "return_reserve",
        "other_variable_cost",
    ):
        assert getattr(inputs, field) is None


def test_explicit_zero_shipping_differs_from_none():
    zero_shipping = make_inputs(seller_shipping_cost=Decimal("0"))
    unknown_shipping = make_inputs()

    assert zero_shipping.seller_shipping_cost == Decimal("0")
    assert unknown_shipping.seller_shipping_cost is None


def test_empty_product_name_rejected():
    with pytest.raises(ValueError):
        make_inputs(product_name="   ")
