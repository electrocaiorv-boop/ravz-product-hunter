from decimal import ROUND_HALF_UP, Decimal

import pytest

from src.margin_analysis import TWO_PLACES, analyze_margin
from src.margin_models import MarginInputs


def make_inputs(**overrides):
    base = dict(product_name="Bebedouro", sale_price=Decimal("100"), product_cost=Decimal("50"))
    base.update(overrides)
    return MarginInputs(**base)


# --- Worked example from CLAUDE.md: price=100, cost=50, fee=15, shipping=10 ---


def test_worked_example_profitable_product():
    inputs = make_inputs(
        marketplace_fee_amount=Decimal("15"),
        seller_shipping_cost=Decimal("10"),
    )
    result = analyze_margin(inputs)

    assert result.gross_profit == Decimal("50.00")
    assert result.gross_margin_percent == Decimal("50.00")
    assert result.markup_percent == Decimal("100.00")
    assert result.total_variable_cost == Decimal("75.00")
    assert result.contribution_profit == Decimal("25.00")
    assert result.contribution_margin_percent == Decimal("25.00")
    # 50% margin != 100% markup -- same profit, different denominators.
    assert result.gross_margin_percent != result.markup_percent
    # Only 2 of 8 optional categories known (25%) -- below the 50% minimum.
    assert result.margin_score is None
    assert any("Margin Score withheld" in note for note in result.notes)


def test_break_even_product_with_fixed_costs():
    inputs = make_inputs(
        product_cost=Decimal("50"),
        marketplace_fee_amount=Decimal("30"),
        seller_shipping_cost=Decimal("20"),
        packaging_cost=Decimal("0"),
        payment_cost=Decimal("0"),
    )
    result = analyze_margin(inputs)

    assert result.contribution_profit == Decimal("0.00")
    assert result.contribution_margin_percent == Decimal("0.00")
    assert result.margin_score == pytest.approx(15.0)  # anchor at 0%


def test_loss_making_product():
    inputs = make_inputs(
        product_cost=Decimal("90"),
        marketplace_fee_amount=Decimal("20"),
        seller_shipping_cost=Decimal("0"),
        packaging_cost=Decimal("0"),
        payment_cost=Decimal("0"),
    )
    result = analyze_margin(inputs)

    assert result.contribution_profit == Decimal("-10.00")
    assert result.contribution_margin_percent == Decimal("-10.00")
    assert result.margin_score == pytest.approx(0.0)  # floor anchor at -10%


def test_zero_product_cost_edge_case():
    inputs = make_inputs(product_cost=Decimal("0"))
    result = analyze_margin(inputs)

    assert result.gross_profit == Decimal("100.00")
    assert result.gross_margin_percent == Decimal("100.00")
    assert result.markup_percent is None
    assert any("markup is undefined" in note for note in result.notes)


# --- Individual cost categories -------------------------------------------


def test_marketplace_fee_amount_used_directly():
    inputs = make_inputs(marketplace_fee_amount=Decimal("15"))
    result = analyze_margin(inputs)
    assert result.marketplace_fee_total == Decimal("15.00")


def test_marketplace_fee_rate_computed_from_sale_price():
    inputs = make_inputs(marketplace_fee_rate=Decimal("0.12"))
    result = analyze_margin(inputs)
    assert result.marketplace_fee_total == Decimal("12.00")  # 100 * 0.12


def test_fixed_marketplace_fee_stacks_with_rate():
    inputs = make_inputs(marketplace_fee_rate=Decimal("0.10"), fixed_marketplace_fee=Decimal("5"))
    result = analyze_margin(inputs)
    assert result.marketplace_fee_total == Decimal("15.00")  # 100*0.10 + 5


def test_shipping_cost_included_in_variable_cost():
    inputs = make_inputs(seller_shipping_cost=Decimal("10"))
    result = analyze_margin(inputs)
    assert result.total_variable_cost == Decimal("60.00")  # 50 + 10


def test_packaging_cost_included_in_variable_cost():
    inputs = make_inputs(packaging_cost=Decimal("3"))
    result = analyze_margin(inputs)
    assert result.total_variable_cost == Decimal("53.00")


def test_tax_amount_used_directly():
    inputs = make_inputs(tax_amount=Decimal("8"))
    result = analyze_margin(inputs)
    assert result.tax_total == Decimal("8.00")


def test_tax_rate_computed_from_sale_price():
    inputs = make_inputs(tax_rate=Decimal("0.06"))
    result = analyze_margin(inputs)
    assert result.tax_total == Decimal("6.00")  # 100 * 0.06


def test_advertising_cost_included_in_variable_cost():
    inputs = make_inputs(advertising_cost_per_sale=Decimal("4"))
    result = analyze_margin(inputs)
    assert result.total_variable_cost == Decimal("54.00")


def test_return_reserve_included_in_variable_cost():
    inputs = make_inputs(return_reserve=Decimal("2"))
    result = analyze_margin(inputs)
    assert result.total_variable_cost == Decimal("52.00")


def test_other_variable_cost_included_in_variable_cost():
    inputs = make_inputs(other_variable_cost=Decimal("1"))
    result = analyze_margin(inputs)
    assert result.total_variable_cost == Decimal("51.00")


# --- Missing vs. known-zero preservation -----------------------------------


def test_missing_optional_costs_are_excluded_and_listed_unavailable():
    inputs = make_inputs()
    result = analyze_margin(inputs)

    assert result.total_variable_cost == Decimal("50.00")  # product_cost only
    assert "marketplace fee" in result.unavailable
    assert "seller shipping cost" in result.unavailable
    assert "packaging cost" in result.unavailable
    assert "tax" in result.unavailable
    assert "payment cost" in result.unavailable
    assert "advertising cost per sale" in result.unavailable
    assert "return/refund reserve" in result.unavailable
    assert "other variable cost" in result.unavailable
    assert result.cost_completeness_score == pytest.approx(0.0)


def test_explicit_zero_marketplace_fee_rate_differs_from_unknown_fee():
    """A derived category (fee from rate) must preserve the same
    missing-vs-zero distinction as a raw field."""
    zero_rate = analyze_margin(make_inputs(marketplace_fee_rate=Decimal("0")))
    unknown_fee = analyze_margin(make_inputs())

    assert zero_rate.marketplace_fee_total == Decimal("0.00")
    assert "marketplace fee" not in zero_rate.unavailable
    assert unknown_fee.marketplace_fee_total is None
    assert "marketplace fee" in unknown_fee.unavailable


def test_explicit_zero_shipping_differs_from_unknown_shipping():
    zero_shipping = analyze_margin(make_inputs(seller_shipping_cost=Decimal("0")))
    unknown_shipping = analyze_margin(make_inputs())

    assert "seller shipping cost" not in zero_shipping.unavailable
    assert zero_shipping.total_variable_cost == Decimal("50.00")  # 50 + 0
    assert "seller shipping cost" in unknown_shipping.unavailable
    assert unknown_shipping.total_variable_cost == Decimal("50.00")  # excluded, not added as 0
    # Same numeric total here by coincidence (0 contributes nothing either
    # way) -- the real difference is completeness and the unavailable list.
    assert zero_shipping.cost_completeness_score > unknown_shipping.cost_completeness_score


# --- Decimal precision and rounding ----------------------------------------


def test_decimal_precision_avoids_float_drift():
    """0.1 + 0.1 + 0.1 must equal exactly 0.3 with Decimal (unlike float)."""
    inputs = make_inputs(
        sale_price=Decimal("1"),
        product_cost=Decimal("0"),
        seller_shipping_cost=Decimal("0.1"),
        packaging_cost=Decimal("0.1"),
        other_variable_cost=Decimal("0.1"),
    )
    result = analyze_margin(inputs)
    assert result.total_variable_cost == Decimal("0.30")
    assert result.contribution_profit == Decimal("0.70")


def test_rounding_uses_round_half_up_deterministically():
    inputs = make_inputs(marketplace_fee_rate=Decimal("0.12345"))
    result = analyze_margin(inputs)
    # 100 * 0.12345 = 12.345 -> half-up on the third decimal rounds to 12.35
    assert result.marketplace_fee_total == Decimal("12.35")


def test_rounding_handles_exact_half_cent_without_float_error():
    """Decimal('2.005') is exact; float would store it as ~2.00499999999999989."""
    inputs = make_inputs(marketplace_fee_amount=Decimal("2.005"))
    result = analyze_margin(inputs)
    assert result.marketplace_fee_total == Decimal("2.01")


def test_result_monetary_fields_are_rounded_to_two_places():
    inputs = make_inputs(marketplace_fee_rate=Decimal("0.0333"))
    result = analyze_margin(inputs)
    assert result.marketplace_fee_total == result.marketplace_fee_total.quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )


# --- Break-even -------------------------------------------------------------


def test_break_even_with_only_fixed_costs():
    inputs = make_inputs(
        product_cost=Decimal("50"),
        marketplace_fee_amount=Decimal("15"),
        seller_shipping_cost=Decimal("10"),
    )
    result = analyze_margin(inputs)

    expected = Decimal("75.00")  # 50 + 15 + 10, no percentage fees
    assert result.break_even_price == expected

    # Round-trip: at that exact price, with the same fixed costs, contribution profit is 0.
    at_break_even = analyze_margin(make_inputs(sale_price=expected, product_cost=Decimal("50"),
                                                marketplace_fee_amount=Decimal("15"),
                                                seller_shipping_cost=Decimal("10")))
    assert at_break_even.contribution_profit == Decimal("0.00")


def test_break_even_with_percentage_fees():
    inputs = make_inputs(
        product_cost=Decimal("50"),
        marketplace_fee_rate=Decimal("0.10"),
        tax_rate=Decimal("0.05"),
        seller_shipping_cost=Decimal("10"),
    )
    result = analyze_margin(inputs)

    fixed_total = Decimal("60")  # 50 + 10
    rate_sum = Decimal("0.15")  # 0.10 + 0.05
    expected = (fixed_total / (Decimal("1") - rate_sum)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    assert result.break_even_price == expected


def test_break_even_impossible_denominator_handled_safely():
    inputs = make_inputs(marketplace_fee_rate=Decimal("0.6"), tax_rate=Decimal("0.5"))
    result = analyze_margin(inputs)

    assert result.break_even_price is None
    assert any("break-even is impossible" in note for note in result.notes)


def test_break_even_denominator_exactly_zero_handled_safely():
    inputs = make_inputs(marketplace_fee_rate=Decimal("0.5"), tax_rate=Decimal("0.5"))
    result = analyze_margin(inputs)

    assert result.break_even_price is None


# --- Cost completeness / Margin Score gating -------------------------------


def test_incomplete_costs_do_not_fabricate_a_score():
    inputs = make_inputs(seller_shipping_cost=Decimal("10"))  # only 1 of 8 known
    result = analyze_margin(inputs)

    assert result.cost_completeness_score == pytest.approx(12.5)
    assert result.margin_score is None
    assert result.contribution_profit is not None  # known-cost metrics still shown


def test_score_produced_once_completeness_threshold_is_met():
    inputs = make_inputs(
        marketplace_fee_amount=Decimal("10"),
        seller_shipping_cost=Decimal("5"),
        packaging_cost=Decimal("5"),
        payment_cost=Decimal("5"),
    )  # 4 of 8 known = 50%, meets the minimum
    result = analyze_margin(inputs)

    assert result.cost_completeness_score == pytest.approx(50.0)
    assert result.margin_score is not None


# --- Determinism and score boundaries ---------------------------------------


def test_identical_inputs_produce_identical_results():
    inputs = make_inputs(marketplace_fee_amount=Decimal("15"), seller_shipping_cost=Decimal("10"))
    assert analyze_margin(inputs) == analyze_margin(inputs)


def test_margin_score_caps_at_100_for_very_high_margin():
    inputs = make_inputs(
        sale_price=Decimal("1000"),
        product_cost=Decimal("10"),
        marketplace_fee_amount=Decimal("10"),
        seller_shipping_cost=Decimal("5"),
        packaging_cost=Decimal("5"),
        payment_cost=Decimal("5"),
    )
    result = analyze_margin(inputs)
    assert result.margin_score == pytest.approx(100.0)


def test_margin_score_floors_at_0_for_very_negative_margin():
    inputs = make_inputs(
        sale_price=Decimal("10"),
        product_cost=Decimal("50"),
        marketplace_fee_amount=Decimal("5"),
        seller_shipping_cost=Decimal("5"),
        packaging_cost=Decimal("5"),
        payment_cost=Decimal("5"),
    )
    result = analyze_margin(inputs)
    assert result.margin_score == pytest.approx(0.0)


@pytest.mark.parametrize(
    "contribution_margin_percent",
    [Decimal("-10"), Decimal("0"), Decimal("5"), Decimal("10"), Decimal("20"), Decimal("30"), Decimal("50")],
)
def test_margin_score_always_within_0_to_100(contribution_margin_percent):
    from src.margin_analysis import _interpolate_margin_score

    score = _interpolate_margin_score(contribution_margin_percent)
    assert 0.0 <= score <= 100.0
